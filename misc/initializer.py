"""
Initializer module for setting up configuration, reading data, 
performing draws, and exporting results.
"""
import logging
import time
import traceback
from datetime import datetime

from yaspin import yaspin

from data_io.input_reader import read_players, read_draw_data
from data_io.output_writer import (
    write_to_csv,
    write_report_csv,
    prepare_report,
    prepare_export_from_group_draw,
    prepare_export_from_bracket_draw,
    archive_previous_outputs,
)

from draw.group_drawer import draw_groups_monte_carlo
from draw.bracket_drawer import draw_bracket, bracket_quality

from misc.config import config
from misc.version import __version__

from checks.validity_checker import check_all_players_only_exist_once, find_missing_players, find_players_not_in_draw_data, find_players_in_wrong_competition, find_draw_data_errors
from checks.group_checker import check_country_distribution, check_base_uniqueness, get_qttr_violations, check_team_country_distribution

_RED = "\033[91m"
_RESET = "\033[0m"

singles_groups = {}
doubles_groups = {}
mixed_groups = {}

singles_brackets = {}
doubles_brackets = {}
mixed_brackets = {}

def initialize_data():
    """Initialize data by reading players and draw data, performing draws, and preparing export.

    Returns True when the pipeline ran to its end (possibly with warnings), False
    when a stage aborted it -- then no current output.csv / HTML exist, because
    stage 0 moved the previous run's files to `previous/`.
    """
    pipeline_start = time.perf_counter()
    # (competition, class, message) per failed group class / bracket.
    bracket_failures = []
    group_failures = []
    # Red lines printed under a bracket section's spinner: failures, degrades
    # and hard-rule violations.
    bracket_problems = []

    def draw_bracket_with_snapshot_fallback(class_subset, competition, competition_class, bracket_kind):
        """Draw one bracket and return its section dict.

        The dict carries `matches`, `snapshots`, `draw_seconds` and `quality`
        (`bracket_drawer.bracket_quality`, or `{"failed": True, "message": ...}`).
        The elapsed time is reported on the failure path too, so a bracket that
        exhausted its attempts still shows how long that search took.
        """
        label = f"{competition} {competition_class} {bracket_kind}"
        start = time.perf_counter()
        try:
            matches, snapshots = draw_bracket(class_subset=class_subset)
            quality = bracket_quality(snapshots)
            if quality["degraded"]:
                bracket_problems.append(f"{label}: DEGRADED (best-effort layout, separations were only soft goals)")
            for rule, violations in quality["hard"].items():
                for violation in violations:
                    bracket_problems.append(f"{label}: {rule}: {violation}")
            for line in quality["bye_order"]:
                bracket_problems.append(f"{label}: bye_order: {line}")
            return {'matches': matches, 'snapshots': snapshots,
                    'draw_seconds': time.perf_counter() - start, 'quality': quality}
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
            return {'matches': {}, 'snapshots': snapshots,
                    'draw_seconds': time.perf_counter() - start,
                    'quality': {"failed": True, "message": failure_message}}

    def draw_groups_with_fallback(class_subset, competition, competition_class):
        """Draw the groups of one class, returning (group, snapshots, elapsed_seconds), or None on failure.

        A failure is recorded in group_failures instead of aborting the run, so the
        other classes are still drawn and exported.
        """
        start = time.perf_counter()
        try:
            group, snapshots = draw_groups_monte_carlo(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
            return group, snapshots, time.perf_counter() - start
        except Exception as exc:
            group_failures.append((competition, competition_class, str(exc)))
            logging.error("Group draw failed for %s %s:\n%s", competition, competition_class, traceback.format_exc())
            return None

    def report_group_section(spinner, label, failures_start, competition_classes):
        """Finish a group draw spinner, as a warning if any class of this section failed."""
        section_failures = [f"{c} {cls}: {msg}" for c, cls, msg in group_failures[failures_start:]]
        if section_failures:
            spinner.text = f"{label} group draw completed with {len(section_failures)} failure(s): {section_failures}"
            spinner.ok("WARN")
        else:
            spinner.text = f"Successfully created {label.lower()} groups for competition classes {list(competition_classes)}"
            spinner.ok()

    def report_bracket_section(spinner, label, problems_start, competition_classes):
        """Finish a bracket draw spinner; WARN and list every failed, degraded or
        rule-breaking bracket of this section in red below it."""
        section_problems = bracket_problems[problems_start:]
        if section_problems:
            spinner.text = f"{label} brackets: {len(section_problems)} problem(s), see below"
            spinner.ok("WARN")
            for problem in section_problems:
                print(f"{_RED}    {problem}{_RESET}")
        else:
            spinner.text = f"Successfully created {label.lower()} bracket for competition classes {list(competition_classes)}"
            spinner.ok()

    ########################################################################################
    with yaspin(text="Moving previous outputs to 'previous'...", color="cyan") as spinner:
        try:
            moved = archive_previous_outputs()
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
            # Read draw data from CSV file
            draw_data = read_draw_data()
            
            # Filter out single draw data
            singles_draw_data = [data for data in draw_data if data.competition == 'S']
            singles_group_draw_data = [data for data in singles_draw_data if data.group_pos is None]
            singles_bracket_draw_data = [data for data in singles_draw_data if data.group_pos is not None]

            # Filter out doubles draw data
            doubles_draw_data = [data for data in draw_data if data.competition == 'D']
            doubles_group_draw_data = [data for data in doubles_draw_data if data.group_pos is None]
            doubles_bracket_draw_data = [data for data in doubles_draw_data if data.group_pos is not None]

            # Filter out mixed draw data
            mixed_draw_data = [data for data in draw_data if data.competition == 'M']
            mixed_group_draw_data = [data for data in mixed_draw_data if data.group_pos is None]
            mixed_bracket_draw_data = [data for data in mixed_draw_data if data.group_pos is not None]


            spinner.text = f"Successfully imported {len(draw_data)} ({len(singles_draw_data)} single, {len(doubles_draw_data)} double, {len(mixed_draw_data)} mixed) draw data objects"
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
                spinner.text = f"There were players imported that are not partaking in any competition: {players_not_in_draw_data}"
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
    with yaspin(text="Drawing singles groups...", color="cyan") as spinner:
        try:
            if not singles_group_draw_data:
                spinner.text = "No singles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                failures_start = len(group_failures)
                singles_competition_classes = sorted(set(data.competition_class for data in singles_group_draw_data))
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_group_draw_data if data.competition_class == competition_class]
                    result = draw_groups_with_fallback(class_subset, 'S', competition_class)
                    if result is None:
                        continue
                    group, snapshots, draw_seconds = result
                    singles_groups[competition_class] = {"group": group, "snapshots": snapshots, "draw_seconds": draw_seconds, "original_data": class_subset}

                report_group_section(spinner, "Singles", failures_start, singles_competition_classes)

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return False

    ########################################################################################
    with yaspin(text="Drawing doubles groups...", color="cyan") as spinner:
        try:
            if not doubles_group_draw_data:
                spinner.text = "No doubles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                failures_start = len(group_failures)
                doubles_competition_classes = sorted(set(data.competition_class for data in doubles_group_draw_data))
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_group_draw_data if data.competition_class == competition_class]
                    result = draw_groups_with_fallback(class_subset, 'D', competition_class)
                    if result is None:
                        continue
                    group, snapshots, draw_seconds = result
                    doubles_groups[competition_class] = {"group": group, "snapshots": snapshots, "draw_seconds": draw_seconds}

                report_group_section(spinner, "Doubles", failures_start, doubles_competition_classes)

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return False


    ########################################################################################
    with yaspin(text="Drawing mixed groups...", color="cyan") as spinner:
        try:
            if not mixed_group_draw_data:
                spinner.text = "No mixed draw group data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                failures_start = len(group_failures)
                mixed_competition_classes = sorted(set(data.competition_class for data in mixed_group_draw_data))
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_group_draw_data if data.competition_class == competition_class]
                    result = draw_groups_with_fallback(class_subset, 'M', competition_class)
                    if result is None:
                        continue
                    group, snapshots, draw_seconds = result
                    mixed_groups[competition_class] = {"group": group, "snapshots": snapshots, "draw_seconds": draw_seconds}

                report_group_section(spinner, "Mixed", failures_start, mixed_competition_classes)

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return False

    ########################################################################################
    with yaspin(text="Validating group draws...", color="cyan") as spinner:
        try:
            invalid_groups = []
            for group_type, group_dict in [('S', singles_groups), ('D', doubles_groups), ('M', mixed_groups)]:
                for competition_class, group_data in group_dict.items():
                    country_violations = check_country_distribution(group_type, group_data["group"])
                    base_violations = check_base_uniqueness(group_data["group"])
                    team_country_violations = check_team_country_distribution(group_data["group"]) if group_type in ('D', 'M') else []
                    qttr_violations = get_qttr_violations(group_data["group"]) if group_type == 'S' else []

                    # Carried into the draw report next to the bracket rows.
                    group_data["violation_count"] = (
                        len(country_violations) + len(base_violations)
                        + len(team_country_violations) + len(qttr_violations)
                    )
                    if group_data["violation_count"]:
                        invalid_groups.append((group_type, competition_class, group_data["group"]))

                    if country_violations:
                        spinner.text = f"Country distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in country_violations:
                            print(f"Country distribution violation in {group_type}: class={competition_class}, country={v[0]}, max={v[1]}, min={v[2]}, group_counts={v[3]}")
                    if base_violations:
                        spinner.text = f"Base uniqueness violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in base_violations:
                            print(f"Base uniqueness violation in {group_type}: class={competition_class}, group={v[0]}, base={v[1]}, count={v[2]}")
                    if team_country_violations:
                        spinner.text = f"Team country distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in team_country_violations:
                            print(f"Team country distribution violation in {group_type}: class={competition_class}, team_type={v[0]}, country={v[1]}, max={v[3]}, min={v[2]}, group_counts={v[4]}")
                    if qttr_violations:
                        spinner.text = f"QTTR distribution violations detected in {group_type}!"
                        spinner.fail("WARN")
                        for v in qttr_violations:
                            print(f"Distribution of players without QTTR rating in {group_type}: class={competition_class}, group={v[0]} - {v[1]} players without QTTR. Distribution: {v[2]}")

            if not invalid_groups:
                spinner.text = "All group draws passed validation checks."
                spinner.ok()
        except Exception as e:
            spinner.fail()
            print("An error occurred during group validation:", e)
            return False

    ########################################################################################
    with yaspin(text="Drawing singles bracket...", color="cyan") as spinner:
        try:
            if not singles_bracket_draw_data:
                spinner.text = "No singles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                problems_start = len(bracket_problems)
                # Create data subsets for each distinct competition class
                singles_competition_classes = sorted(set(data.competition_class for data in singles_bracket_draw_data))
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    singles_brackets[competition_class] = {
                        'main': draw_bracket_with_snapshot_fallback(
                            class_subset=main_round_participants,
                            competition='S',
                            competition_class=competition_class,
                            bracket_kind='main',
                        ),
                        'consolation': draw_bracket_with_snapshot_fallback(
                            class_subset=consolation_round_participants,
                            competition='S',
                            competition_class=competition_class,
                            bracket_kind='consolation',
                        ),
                    }

                report_bracket_section(spinner, "Singles", problems_start, singles_competition_classes)

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return False

    ########################################################################################
    with yaspin(text="Drawing doubles bracket...", color="cyan") as spinner:
        try:
            if not doubles_bracket_draw_data:
                spinner.text = "No doubles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                problems_start = len(bracket_problems)
                # Create data subsets for each distinct competition class
                doubles_competition_classes = sorted(set(data.competition_class for data in doubles_bracket_draw_data))
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    doubles_brackets[competition_class] = {
                        'main': draw_bracket_with_snapshot_fallback(
                            class_subset=main_round_participants,
                            competition='D',
                            competition_class=competition_class,
                            bracket_kind='main',
                        ),
                        'consolation': draw_bracket_with_snapshot_fallback(
                            class_subset=consolation_round_participants,
                            competition='D',
                            competition_class=competition_class,
                            bracket_kind='consolation',
                        ),
                    }

                report_bracket_section(spinner, "Doubles", problems_start, doubles_competition_classes)

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return False

    ########################################################################################
    with yaspin(text="Drawing mixed bracket...", color="cyan") as spinner:
        try:
            if not mixed_bracket_draw_data:
                spinner.text = "No mixed bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                problems_start = len(bracket_problems)
                # Create data subsets for each distinct competition class
                mixed_competition_classes = sorted(set(data.competition_class for data in mixed_bracket_draw_data))
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    mixed_brackets[competition_class] = {
                        'main': draw_bracket_with_snapshot_fallback(
                            class_subset=main_round_participants,
                            competition='M',
                            competition_class=competition_class,
                            bracket_kind='main',
                        ),
                        'consolation': draw_bracket_with_snapshot_fallback(
                            class_subset=consolation_round_participants,
                            competition='M',
                            competition_class=competition_class,
                            bracket_kind='consolation',
                        ),
                    }

                report_bracket_section(spinner, "Mixed", problems_start, mixed_competition_classes)

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return False

    ########################################################################################
    bracket_payload = {
        'S': singles_brackets,
        'D': doubles_brackets,
        'M': mixed_brackets,
    }

    export_data = []

    with yaspin(text="Preparing data for export...", color="cyan") as spinner:
        try:
            groups = {'S': singles_groups, 'D': doubles_groups, 'M': mixed_groups}
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
    with yaspin(text="Exporting groups and brackets to HTML...", color="cyan") as spinner:
        from viewer.bracket_html_exporter import export_bracket_html
        from viewer.group_html_exporter import export_group_html
        bracket_output_dir = config["files"].get("bracket_html_output_dir", "output/brackets")
        group_output_dir = config["files"].get("group_html_output_dir", "output/groups")
        html_failures = []
        try:
            group_max_snapshots = int(config["group_draw"].get("html_max_snapshots", 20000))
        except ValueError:
            group_max_snapshots = 20000
        # Read the total once, before the export loop, so every exported file
        # reports the same run duration and none of them include the cost of
        # writing the HTML itself.
        run_meta = {
            'version': __version__,
            'total_seconds': time.perf_counter() - pipeline_start,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'random_seed': config["settings"].get("random_seed") or None,
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
                    logging.error("Group HTML export failed for %s %s:\n%s", competition, competition_class, traceback.format_exc())

        for competition, brackets in bracket_payload.items():
            for competition_class, bracket in brackets.items():
                try:
                    export_bracket_html(competition, competition_class, bracket, bracket_output_dir, run_meta=run_meta)
                except Exception:
                    html_failures.append(f"{competition} {competition_class} brackets")
                    logging.error("Bracket HTML export failed for %s %s:\n%s", competition, competition_class, traceback.format_exc())

        if html_failures:
            spinner.text = f"HTML export completed with {len(html_failures)} failure(s): {html_failures}"
            spinner.ok("WARN")
        else:
            spinner.text = "Successfully exported groups and brackets to HTML"
            spinner.ok()

    return True
