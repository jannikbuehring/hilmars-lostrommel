"""The draw pipeline: read the input, validate it, draw every group and bracket, and export the results."""

import logging
import time
import traceback
from datetime import datetime

from yaspin import yaspin

from app.progress_spinner import detail_spinner
from checks.group_checker import (
    check_base_uniqueness,
    check_country_distribution,
    check_team_country_distribution,
    get_qttr_violations,
)
from checks.validity_checker import (
    check_all_players_only_exist_once,
    find_draw_data_errors,
    find_missing_players,
    find_players_in_wrong_competition,
    find_players_not_in_draw_data,
)
from core.config import settings
from core.version import __version__
from data_io.input_reader import read_draw_data, read_players
from data_io.output_writer import (
    archive_previous_outputs,
    prepare_export_from_bracket_draw,
    prepare_export_from_group_draw,
    prepare_report,
    write_report_csv,
    write_to_csv,
)
from draw.bracket_drawer import bracket_quality, draw_bracket
from draw.group_drawer import draw_groups_monte_carlo
from models.draw_results import COMPETITIONS, DrawResults

_RED = "\033[91m"
_RESET = "\033[0m"


def _by_class(entries):
    """Split draw entries into {competition_class: [entries]}, ordered by class."""
    by_class = {}
    for entry in sorted(entries, key=lambda e: e.competition_class):
        by_class.setdefault(entry.competition_class, []).append(entry)
    return by_class


def initialize_data(results: DrawResults, export_html=True):
    """Read players and draw data, draw every group and bracket into `results`, and export them.

    With `export_html=False` no HTML is written, and the HTML pages of earlier
    runs are neither archived nor overwritten.

    Returns True when the pipeline ran to its end (possibly with warnings), False
    when a stage aborted it -- then no current output.csv / HTML exist, because
    stage 0 moved the previous run's files to `previous/`. `results` keeps
    whatever was drawn before an abort, so the menu can still show it.
    """
    pipeline_start = time.perf_counter()
    # (competition, class, message) per failed group class / bracket.
    bracket_failures = []
    group_failures = []
    # Red lines printed under a bracket section's spinner: failures, degrades
    # and hard-rule violations.
    bracket_problems = []

    def detail_reporter(spinner, label):
        """Progress callback for a drawer: shows `label - message` below the spinner."""

        def report(message):
            spinner.detail = f"{label} - {message}"

        return report

    def draw_bracket_with_snapshot_fallback(spinner, class_subset, competition, competition_class, bracket_kind):
        """Draw one bracket and return its section dict.

        The dict carries `matches`, `snapshots`, `draw_seconds` and `quality`
        (`bracket_drawer.bracket_quality`, or `{"failed": True, "message": ...}`).
        The elapsed time is reported on the failure path too, so a bracket that
        exhausted its attempts still shows how long that search took.
        """
        label = f"{competition} {competition_class} {bracket_kind}"
        start = time.perf_counter()
        try:
            matches, snapshots = draw_bracket(
                class_subset=class_subset,
                progress=detail_reporter(spinner, f"{competition} {competition_class} {bracket_kind} bracket"),
            )
            quality = bracket_quality(snapshots)
            if quality["degraded"]:
                bracket_problems.append(f"{label}: DEGRADED (best-effort layout, separations were only soft goals)")
            for rule, violations in quality["hard"].items():
                for violation in violations:
                    bracket_problems.append(f"{label}: {rule}: {violation}")
            for line in quality["bye_order"]:
                bracket_problems.append(f"{label}: bye_order: {line}")
            for line in quality["balance"]:
                bracket_problems.append(f"{label}: imbalanced: {line}")
            return {
                "matches": matches,
                "snapshots": snapshots,
                "draw_seconds": time.perf_counter() - start,
                "quality": quality,
            }
        except Exception as exc:
            snapshots = getattr(exc, "snapshots", [])
            failure_snapshot = getattr(exc, "failure_snapshot", snapshots[-1] if snapshots else None)
            failure_message = str(exc)
            if failure_snapshot is not None:
                failure_info = getattr(failure_snapshot, "violations", {}).get("failure", {})
                if isinstance(failure_info, dict):
                    failure_message = failure_info.get("message", failure_message)

            bracket_failures.append((competition, competition_class, failure_message))
            bracket_problems.append(f"{label}: FAILED: {failure_message}")
            logging.error(
                "Bracket draw failed for %s %s %s: %s",
                competition,
                competition_class,
                bracket_kind,
                failure_message,
            )
            # Keep matches empty so failed brackets are not exported as real draws.
            # Snapshots are preserved for interactive debugging.
            return {
                "matches": {},
                "snapshots": snapshots,
                "draw_seconds": time.perf_counter() - start,
                "quality": {"failed": True, "message": failure_message},
            }

    def draw_groups_with_fallback(spinner, class_subset, competition, competition_class, class_no, class_count):
        """Draw the groups of one class, returning (group, snapshots, elapsed_seconds), or None on failure.

        A failure is recorded in group_failures instead of aborting the run, so the
        other classes are still drawn and exported.  class_no/class_count only
        label the progress line below the spinner ("S M1 (class 2 of 4)").
        """
        start = time.perf_counter()
        try:
            group, snapshots = draw_groups_monte_carlo(
                class_subset=class_subset,
                amount_of_groups=class_subset[0].amount_of_groups,
                progress=detail_reporter(
                    spinner, f"{competition} {competition_class} (class {class_no} of {class_count})"
                ),
            )
            return group, snapshots, time.perf_counter() - start
        except Exception as exc:
            group_failures.append((competition, competition_class, str(exc)))
            logging.error("Group draw failed for %s %s:\n%s", competition, competition_class, traceback.format_exc())
            return None

    def report_group_section(spinner, label, failures_start, competition_classes):
        """Finish a group draw spinner, as a warning if any class of this section failed."""
        spinner.detail = None
        section_failures = [f"{c} {cls}: {msg}" for c, cls, msg in group_failures[failures_start:]]
        if section_failures:
            spinner.text = f"{label} group draw completed with {len(section_failures)} failure(s): {section_failures}"
            spinner.ok("WARN")
        else:
            spinner.text = (
                f"Successfully created {label.lower()} groups for competition classes {list(competition_classes)}"
            )
            spinner.ok()

    def report_bracket_section(spinner, label, problems_start, competition_classes):
        """Finish a bracket draw spinner; WARN and list every failed, degraded or
        rule-breaking bracket of this section in red below it."""
        spinner.detail = None
        section_problems = bracket_problems[problems_start:]
        if section_problems:
            spinner.text = f"{label} brackets: {len(section_problems)} problem(s), see below"
            spinner.ok("WARN")
            for problem in section_problems:
                print(f"{_RED}    {problem}{_RESET}")
        else:
            spinner.text = (
                f"Successfully created {label.lower()} bracket for competition classes {list(competition_classes)}"
            )
            spinner.ok()

    def draw_group_section(code, label, entries):
        """Draw every group class of one competition into results.groups[code]. False aborts the run."""
        with detail_spinner(f"Drawing {label.lower()} groups...") as spinner:
            try:
                if not entries:
                    spinner.text = f"No {label.lower()} group draw data found - no groups created"
                    spinner.fail("INFO")
                    return True
                failures_start = len(group_failures)
                classes = _by_class(entries)
                for class_no, (competition_class, class_subset) in enumerate(classes.items(), start=1):
                    result = draw_groups_with_fallback(
                        spinner, class_subset, code, competition_class, class_no, len(classes)
                    )
                    if result is None:
                        continue
                    group, snapshots, draw_seconds = result
                    results.groups[code][competition_class] = {
                        "group": group,
                        "snapshots": snapshots,
                        "draw_seconds": draw_seconds,
                    }
                report_group_section(spinner, label, failures_start, classes)
                return True
            except Exception as e:
                spinner.fail()
                print("An error occurred:", e)
                return False

    def draw_bracket_section(code, label, entries):
        """Draw the main and consolation bracket of every class into results.brackets[code]. False aborts the run."""
        with detail_spinner(f"Drawing {label.lower()} bracket...") as spinner:
            try:
                if not entries:
                    spinner.text = f"No {label.lower()} bracket draw data found - no bracket created"
                    spinner.fail("INFO")
                    return True
                problems_start = len(bracket_problems)
                classes = _by_class(entries)
                for competition_class, class_subset in classes.items():
                    results.brackets[code][competition_class] = {
                        kind: draw_bracket_with_snapshot_fallback(
                            spinner,
                            class_subset=[e for e in class_subset if getattr(e, flag)],
                            competition=code,
                            competition_class=competition_class,
                            bracket_kind=kind,
                        )
                        for kind, flag in (("main", "main_round"), ("consolation", "consolation_round"))
                    }
                report_bracket_section(spinner, label, problems_start, classes)
                return True
            except Exception as e:
                spinner.fail()
                logging.error("An error occurred: %s", e)
                return False

    ########################################################################################
    with yaspin(text="Moving previous outputs to 'previous'...", color="cyan") as spinner:
        try:
            moved = archive_previous_outputs(include_html=export_html)
            spinner.text = f"Moved {len(moved)} file(s) of the previous run to 'previous'"
            spinner.ok()
        except PermissionError as exc:
            spinner.text = f"Cannot move {exc.filename} - close it (e.g. in Excel) and restart"
            spinner.fail()
            return False
        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return False

    ########################################################################################
    with yaspin(text="Reading player data...", color="cyan") as spinner:
        try:
            players = read_players()
            spinner.text = f"Successfully imported {len(players)} players"
            spinner.ok()

        except FileNotFoundError:
            spinner.text = "Players file not found"
            spinner.fail()
            return False

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return False

    ########################################################################################
    with yaspin(text="Reading draw data...", color="cyan") as spinner:
        try:
            draw_data = read_draw_data()
            # {competition: (group-stage entries, bracket-stage entries)}
            entries = {
                code: (
                    [d for d in draw_data if d.competition == code and d.group_pos is None],
                    [d for d in draw_data if d.competition == code and d.group_pos is not None],
                )
                for code, _ in COMPETITIONS
            }
            counts = {code: sum(len(stage) for stage in entries[code]) for code, _ in COMPETITIONS}
            spinner.text = f"Successfully imported {len(draw_data)} ({counts['S']} single, {counts['D']} double, {counts['M']} mixed) draw data objects"
            spinner.ok()

        except FileNotFoundError:
            spinner.text = "Draw input file not found"
            spinner.fail()
            return False

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return False

    ########################################################################################
    with yaspin(text="Performing data validity checks...", color="cyan") as spinner:
        try:
            wrongful_player_data = check_all_players_only_exist_once()
            if wrongful_player_data:
                spinner.text = "There were multiple player entries found"
                spinner.fail()
                print(f">>>> Multiple player entries for start number(s): {wrongful_player_data}")
                return False

            missing_players = find_missing_players(draw_data)
            if missing_players:
                spinner.text = "The draw data contains references to players that are missing from the import"
                spinner.fail()
                print(f">>>> Missing player(s): {missing_players}")
                return False

            players_not_in_draw_data = find_players_not_in_draw_data(draw_data)
            if players_not_in_draw_data:
                spinner.text = (
                    f"There were players imported that are not partaking in any competition: {players_not_in_draw_data}"
                )
                spinner.ok("WARN")

            errors = find_players_in_wrong_competition(draw_data)
            if errors:
                spinner.text = "Competition integrity problems detected"
                spinner.fail()
                print("")
                for e in errors:
                    print("   ", e)
                return False

            draw_data_errors = find_draw_data_errors(draw_data)
            if draw_data_errors:
                spinner.text = "Draw data integrity problems detected"
                spinner.fail()
                print("")
                for e in draw_data_errors:
                    print("   ", e)
                return False

            spinner.text = "The imported data seems valid"
            spinner.ok()

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return False

    ########################################################################################
    for code, label in COMPETITIONS:
        if not draw_group_section(code, label, entries[code][0]):
            return False

    ########################################################################################
    with yaspin(text="Validating group draws...", color="cyan") as spinner:
        try:
            invalid_groups = []
            for group_type, group_dict in results.groups.items():
                for competition_class, group_data in group_dict.items():
                    country_violations = check_country_distribution(group_type, group_data["group"])
                    base_violations = check_base_uniqueness(group_data["group"])
                    team_country_violations = (
                        check_team_country_distribution(group_data["group"]) if group_type in ("D", "M") else []
                    )
                    qttr_violations = get_qttr_violations(group_data["group"]) if group_type == "S" else []

                    # Carried into the draw report next to the bracket rows.
                    group_data["violation_count"] = (
                        len(country_violations)
                        + len(base_violations)
                        + len(team_country_violations)
                        + len(qttr_violations)
                    )
                    if group_data["violation_count"]:
                        invalid_groups.append((group_type, competition_class, group_data["group"]))

                    if country_violations:
                        spinner.text = f"Country distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in country_violations:
                            print(
                                f"Country distribution violation in {group_type}: class={competition_class}, country={v[0]}, max={v[1]}, min={v[2]}, group_counts={v[3]}"
                            )
                    if base_violations:
                        spinner.text = f"Base uniqueness violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in base_violations:
                            print(
                                f"Base uniqueness violation in {group_type}: class={competition_class}, group={v[0]}, base={v[1]}, count={v[2]}"
                            )
                    if team_country_violations:
                        spinner.text = f"Team country distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in team_country_violations:
                            print(
                                f"Team country distribution violation in {group_type}: class={competition_class}, team_type={v[0]}, country={v[1]}, max={v[3]}, min={v[2]}, group_counts={v[4]}"
                            )
                    if qttr_violations:
                        spinner.text = f"QTTR distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in qttr_violations:
                            print(
                                f"Distribution of players without QTTR rating in {group_type}: class={competition_class}, group={v[0]} - {v[1]} players without QTTR. Distribution: {v[2]}"
                            )

            if not invalid_groups:
                spinner.text = "All group draws passed validation checks."
                spinner.ok()
        except Exception as e:
            spinner.fail()
            print("An error occurred during group validation:", e)
            return False

    ########################################################################################
    for code, label in COMPETITIONS:
        if not draw_bracket_section(code, label, entries[code][1]):
            return False

    ########################################################################################
    groups = results.groups
    bracket_payload = results.brackets
    export_data = []

    with yaspin(text="Preparing data for export...", color="cyan") as spinner:
        try:
            export_data.extend(prepare_export_from_group_draw(groups))
            export_data.extend(prepare_export_from_bracket_draw(bracket_payload))

            spinner.text = f"Export successfully prepared ({len(export_data)} rows)"
            spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return False

    ########################################################################################
    with yaspin(text="Exporting draws to file...", color="cyan") as spinner:
        try:
            output_file_path = write_to_csv(export_data)
            report_path = write_report_csv(prepare_report(groups, group_failures, bracket_payload))

            spinner.text = f"Successfully created output file {output_file_path} and draw report {report_path}"
            spinner.ok()

        except PermissionError as exc:
            spinner.text = f"Cannot write {exc.filename} - close it (e.g. in Excel) and restart"
            spinner.fail()
            return False

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return False

    ########################################################################################
    results.html_exported = export_html
    if not export_html:
        with yaspin(text="Exporting groups and brackets to HTML...", color="cyan") as spinner:
            spinner.text = "Skipped HTML export (--no-html)"
            spinner.ok("INFO")
        return True

    with yaspin(text="Exporting groups and brackets to HTML...", color="cyan") as spinner:
        from viewer.bracket_html_exporter import export_bracket_html
        from viewer.group_html_exporter import export_group_html

        bracket_output_dir = settings.files.bracket_html_output_dir
        group_output_dir = settings.files.group_html_output_dir
        group_max_snapshots = settings.group_draw.html_max_snapshots
        html_failures = []
        # Read the total once, before the export loop, so every exported file
        # reports the same run duration and none of them include the cost of
        # writing the HTML itself.
        run_meta = {
            "version": __version__,
            "total_seconds": time.perf_counter() - pipeline_start,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "random_seed": settings.general.random_seed or None,
        }
        # Each class is exported on its own, so one failing file does not skip
        # every later one.
        for competition, group_dict in groups.items():
            for competition_class, group_data in group_dict.items():
                try:
                    export_group_html(
                        competition,
                        competition_class,
                        group_data["group"],
                        group_data["snapshots"],
                        group_output_dir,
                        run_meta=run_meta,
                        max_snapshots=group_max_snapshots,
                        draw_seconds=group_data.get("draw_seconds"),
                    )
                except Exception:
                    html_failures.append(f"{competition} {competition_class} groups")
                    logging.error(
                        "Group HTML export failed for %s %s:\n%s",
                        competition,
                        competition_class,
                        traceback.format_exc(),
                    )

        for competition, brackets in bracket_payload.items():
            for competition_class, bracket in brackets.items():
                try:
                    export_bracket_html(competition, competition_class, bracket, bracket_output_dir, run_meta=run_meta)
                except Exception:
                    html_failures.append(f"{competition} {competition_class} brackets")
                    logging.error(
                        "Bracket HTML export failed for %s %s:\n%s",
                        competition,
                        competition_class,
                        traceback.format_exc(),
                    )

        if html_failures:
            spinner.text = f"HTML export completed with {len(html_failures)} failure(s): {html_failures}"
            spinner.ok("WARN")
        else:
            spinner.text = "Successfully exported groups and brackets to HTML"
            spinner.ok()

    return True
