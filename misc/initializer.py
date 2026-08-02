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
from data_io.output_writer import write_to_csv, prepare_export_from_group_draw, prepare_export_from_bracket_draw

from draw.group_drawer import draw_groups_monte_carlo
from draw.bracket_drawer import draw_bracket

from misc.config import config
from misc.version import __version__

from checks.validity_checker import check_all_players_only_exist_once, find_missing_players, find_players_not_in_draw_data, find_players_in_wrong_competition
from checks.group_checker import check_country_distribution, check_base_uniqueness, get_qttr_violations, check_team_country_distribution

export_data = []

singles_groups = {}
doubles_groups = {}
mixed_groups = {}

singles_brackets = {}
doubles_brackets = {}
mixed_brackets = {}

def initialize_data():
    """Initialize data by reading players and draw data, performing draws, and preparing export."""
    pipeline_start = time.perf_counter()
    bracket_failures = []

    def draw_bracket_with_snapshot_fallback(class_subset, competition, competition_class, bracket_kind):
        """Draw one bracket, returning (matches, snapshots, elapsed_seconds).

        The elapsed time is reported on the failure path too, so a bracket that
        exhausted its attempts still shows how long that search took.
        """
        start = time.perf_counter()
        try:
            matches, snapshots = draw_bracket(class_subset=class_subset)
            return matches, snapshots, time.perf_counter() - start
        except Exception as exc:
            snapshots = getattr(exc, "snapshots", [])
            failure_snapshot = getattr(exc, "failure_snapshot", snapshots[-1] if snapshots else None)
            failure_message = str(exc)
            if failure_snapshot is not None:
                failure_info = getattr(failure_snapshot, "violations", {}).get("failure", {})
                if isinstance(failure_info, dict):
                    failure_message = failure_info.get("message", failure_message)

            bracket_failures.append(
                f"{competition} {competition_class} {bracket_kind}: {failure_message}"
            )
            logging.error(
                "Bracket draw failed for %s %s %s: %s",
                competition,
                competition_class,
                bracket_kind,
                failure_message,
            )
            # Keep matches empty so failed brackets are not exported as real draws.
            # Snapshots are preserved for interactive debugging.
            return {}, snapshots, time.perf_counter() - start
    ########################################################################################
    with yaspin(text="Reading player data...", color="cyan") as spinner:
        try:
            players = read_players()
            spinner.text = f"Successfully imported {len(players)} players"
            spinner.ok()

        except FileNotFoundError:
            spinner.text = "Players file not found"
            spinner.fail()
            return

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return

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
            return

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return

    ########################################################################################
    with yaspin(text="Performing data validity checks...", color="cyan") as spinner:
        try:
            wrongful_player_data = check_all_players_only_exist_once()
            if wrongful_player_data:
                spinner.text = "There were multiple player entries found"
                spinner.fail()
                print(f">>>> Multiple player entries for start number(s): {wrongful_player_data}")
                return

            missing_players = find_missing_players(draw_data)
            if missing_players:
                spinner.text = "The draw data contains references to players that are missing from the import"
                spinner.fail()
                print(f">>>> Missing player(s): {missing_players}")
                return

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
                return

            spinner.text = "The imported data seems valid"
            spinner.ok()
                

        except Exception:
            spinner.fail()
            logging.error("Exception occurred:\n%s", traceback.format_exc())
            return


    ########################################################################################
    with yaspin(text="Drawing singles groups...", color="cyan") as spinner:
        try:
            if not singles_group_draw_data:
                spinner.text = "No singles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                singles_competition_classes = sorted(set(data.competition_class for data in singles_group_draw_data))
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = draw_groups_monte_carlo(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    singles_groups[competition_class] = {"group": group, "snapshots": snapshots, "original_data": class_subset}

                competition_classes_list = list(singles_competition_classes)
                spinner.text = f"Successfully created singles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return

    ########################################################################################
    with yaspin(text="Drawing doubles groups...", color="cyan") as spinner:
        try:
            if not doubles_group_draw_data:
                spinner.text = "No doubles group draw data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                doubles_competition_classes = sorted(set(data.competition_class for data in doubles_group_draw_data))
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = draw_groups_monte_carlo(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    doubles_groups[competition_class] = {"group": group, "snapshots": snapshots}

                competition_classes_list = list(doubles_competition_classes)
                spinner.text = f"Successfully created doubles groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return


    ########################################################################################
    with yaspin(text="Drawing mixed groups...", color="cyan") as spinner:
        try:
            if not mixed_group_draw_data:
                spinner.text = "No mixed draw group data found - no groups created"
                spinner.fail("INFO")
            else:
                # Create data subsets for each distinct competition class
                mixed_competition_classes = sorted(set(data.competition_class for data in mixed_group_draw_data))
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_group_draw_data if data.competition_class == competition_class]
                    group, snapshots = draw_groups_monte_carlo(class_subset=class_subset, amount_of_groups=class_subset[0].amount_of_groups)
                    mixed_groups[competition_class] = {"group": group, "snapshots": snapshots}

                competition_classes_list = list(mixed_competition_classes)
                spinner.text = f"Successfully created mixed groups for competition classes {competition_classes_list}"
                spinner.ok()

        except Exception as e:
            spinner.fail()
            print("An error occurred:", e)
            return

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

                    if country_violations or base_violations or team_country_violations or qttr_violations:
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
            return

    ########################################################################################
    with yaspin(text="Drawing singles bracket...", color="cyan") as spinner:
        try:
            if not singles_bracket_draw_data:
                spinner.text = "No singles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                section_failures_start = len(bracket_failures)
                # Create data subsets for each distinct competition class
                singles_competition_classes = sorted(set(data.competition_class for data in singles_bracket_draw_data))
                for competition_class in singles_competition_classes:
                    class_subset = [data for data in singles_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    main_bracket, main_snapshots, main_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=main_round_participants,
                        competition='S',
                        competition_class=competition_class,
                        bracket_kind='main',
                    )
                    consolation_bracket, consolation_snapshots, consolation_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=consolation_round_participants,
                        competition='S',
                        competition_class=competition_class,
                        bracket_kind='consolation',
                    )
                    singles_brackets[competition_class] = {
                        'main': {'matches': main_bracket, 'snapshots': main_snapshots, 'draw_seconds': main_seconds},
                        'consolation': {'matches': consolation_bracket, 'snapshots': consolation_snapshots, 'draw_seconds': consolation_seconds}
                    }

                competition_classes_list = list(singles_competition_classes)
                section_failures = len(bracket_failures) - section_failures_start
                if section_failures:
                    spinner.text = (
                        f"Singles bracket draw completed with {section_failures} failure(s). "
                        f"Use interactive bracket viewer snapshots for details."
                    )
                    spinner.ok("WARN")
                else:
                    spinner.text = f"Successfully created singles bracket for competition classes {competition_classes_list}"
                    spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return

    ########################################################################################
    with yaspin(text="Drawing doubles bracket...", color="cyan") as spinner:
        try:
            if not doubles_bracket_draw_data:
                spinner.text = "No doubles bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                section_failures_start = len(bracket_failures)
                doubles_competition_classes = sorted(set(data.competition_class for data in doubles_bracket_draw_data))
                for competition_class in doubles_competition_classes:
                    class_subset = [data for data in doubles_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]
                    
                    main_bracket, main_snapshots, main_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=main_round_participants,
                        competition='D',
                        competition_class=competition_class,
                        bracket_kind='main',
                    )
                    consolation_bracket, consolation_snapshots, consolation_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=consolation_round_participants,
                        competition='D',
                        competition_class=competition_class,
                        bracket_kind='consolation',
                    )
                    doubles_brackets[competition_class] = {
                        'main': {'matches': main_bracket, 'snapshots': main_snapshots, 'draw_seconds': main_seconds},
                        'consolation': {'matches': consolation_bracket, 'snapshots': consolation_snapshots, 'draw_seconds': consolation_seconds}
                    }

                competition_classes_list = list(doubles_competition_classes)
                section_failures = len(bracket_failures) - section_failures_start
                if section_failures:
                    spinner.text = (
                        f"Doubles bracket draw completed with {section_failures} failure(s). "
                        f"Use interactive bracket viewer snapshots for details."
                    )
                    spinner.ok("WARN")
                else:
                    spinner.text = f"Successfully created doubles bracket for competition classes {competition_classes_list}"
                    spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return

    ########################################################################################
    with yaspin(text="Drawing mixed bracket...", color="cyan") as spinner:
        try:
            if not mixed_bracket_draw_data:
                spinner.text = "No mixed bracket draw data found - no bracket created"
                spinner.fail("INFO")
            else:
                section_failures_start = len(bracket_failures)
                mixed_competition_classes = sorted(set(data.competition_class for data in mixed_bracket_draw_data))
                for competition_class in mixed_competition_classes:
                    class_subset = [data for data in mixed_bracket_draw_data if data.competition_class == competition_class]
                    main_round_participants = [data for data in class_subset if data.main_round == True]
                    consolation_round_participants = [data for data in class_subset if data.consolation_round == True]

                    main_bracket, main_snapshots, main_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=main_round_participants,
                        competition='M',
                        competition_class=competition_class,
                        bracket_kind='main',
                    )
                    consolation_bracket, consolation_snapshots, consolation_seconds = draw_bracket_with_snapshot_fallback(
                        class_subset=consolation_round_participants,
                        competition='M',
                        competition_class=competition_class,
                        bracket_kind='consolation',
                    )
                    mixed_brackets[competition_class] = {
                        'main': {'matches': main_bracket, 'snapshots': main_snapshots, 'draw_seconds': main_seconds},
                        'consolation': {'matches': consolation_bracket, 'snapshots': consolation_snapshots, 'draw_seconds': consolation_seconds}
                    }

                competition_classes_list = list(mixed_competition_classes)
                section_failures = len(bracket_failures) - section_failures_start
                if section_failures:
                    spinner.text = (
                        f"Mixed bracket draw completed with {section_failures} failure(s). "
                        f"Use interactive bracket viewer snapshots for details."
                    )
                    spinner.ok("WARN")
                else:
                    spinner.text = f"Successfully created mixed bracket for competition classes {competition_classes_list}"
                    spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return

    ########################################################################################
    bracket_payload = {
        'S': singles_brackets,
        'D': doubles_brackets,
        'M': mixed_brackets,
    }

    #with yaspin(text="Preparing data for export...", color="cyan") as spinner:
    #    try:
    #        groups = {'S': singles_groups, 'D': doubles_groups, 'M': mixed_groups}
    #        export_data.extend(prepare_export_from_group_draw(groups))
    #        export_data.extend(prepare_export_from_bracket_draw(bracket_payload))

    #         spinner.text = "Export successfully prepared"
    #         spinner.ok()

    #     except Exception as e:
    #         spinner.fail()
    #         logging.error("An error occurred: %s", e)
    #         return

    # ########################################################################################
    # with yaspin(text="Exporting draws to file...", color="cyan") as spinner:
    #     try:
    #         write_to_csv(export_data)

    #         spinner.text = "Successfully created output file"
    #         spinner.ok()

    #     except Exception as e:
    #         spinner.fail()
    #         logging.error("An error occurred: %s", e)
    #         return

    ########################################################################################
    with yaspin(text="Exporting brackets to HTML...", color="cyan") as spinner:
        try:
            from viewer.bracket_html_exporter import export_bracket_html
            output_dir = config["files"].get("bracket_html_output_dir", "output/brackets")
            # Read the total once, before the export loop, so every exported file
            # reports the same run duration and none of them include the cost of
            # writing the HTML itself.
            run_meta = {
                'version': __version__,
                'total_seconds': time.perf_counter() - pipeline_start,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'random_seed': config["settings"].get("random_seed") or None,
            }
            for competition, brackets in bracket_payload.items():
                for competition_class, bracket in brackets.items():
                    export_bracket_html(competition, competition_class, bracket, output_dir, run_meta=run_meta)

            spinner.text = "Successfully exported brackets to HTML"
            spinner.ok()

        except Exception as e:
            spinner.fail()
            logging.error("An error occurred: %s", e)
            return