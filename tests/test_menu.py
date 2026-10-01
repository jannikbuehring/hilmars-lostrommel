"""Tests for app/menu.py navigation."""

import pytest

import app.menu as menu
from models.draw_results import DrawResults


@pytest.fixture
def results():
    results = DrawResults()
    results.groups["D"]["M1"] = {"group": {1: []}, "snapshots": ["s"]}
    results.brackets["S"]["M2"] = {"main": {"matches": {1: []}}}
    return results


@pytest.fixture
def answers(monkeypatch):
    """Feed menu answers in order; record which prompts were shown."""
    queue = []
    prompts = []

    def list_input(message, choices):
        prompts.append((message, choices))
        return queue.pop(0)

    monkeypatch.setattr(menu.inquirer, "list_input", list_input)
    return queue, prompts


def test_opens_the_chosen_group_class(results, answers, monkeypatch):
    queue, prompts = answers
    queue.extend(["Groups", "Doubles", "M1"])
    shown = []
    monkeypatch.setattr(menu, "show_groups", lambda **kwargs: shown.append(kwargs))

    assert menu._view_menu(results) is None

    assert shown == [{"competition": "D", "competition_class": "M1", "groups": {1: []}, "snapshots": ["s"]}]
    assert prompts[-1] == ("Choose a competition class", ["M1", "Back"])


def test_opens_the_chosen_bracket_class(results, answers, monkeypatch):
    queue, _ = answers
    queue.extend(["Bracket", "Singles", "M2"])
    shown = []
    monkeypatch.setattr(menu, "show_bracket", lambda **kwargs: shown.append(kwargs))

    menu._view_menu(results)

    assert shown == [{"competition": "S", "competition_class": "M2", "bracket": results.brackets["S"]["M2"]}]


def test_back_from_class_list_returns_to_the_view_menu(results, answers):
    queue, prompts = answers
    queue.extend(["Groups", "Singles", "Back", "Back"])

    menu._view_menu(results)

    assert [message for message, _ in prompts] == [
        "Choose what to view",
        "Choose what to view",
        "Choose a competition class",
        "Choose what to view",
    ]
    assert prompts[2][1] == ["Back"]


def test_exit_leaves_the_main_menu(results, answers):
    queue, _ = answers
    queue.append("Exit")

    with pytest.raises(SystemExit):
        menu.show_main_menu(results)


def test_without_html_only_players_can_be_viewed(results, answers):
    queue, prompts = answers
    results.html_exported = False
    queue.append("Back")

    menu._view_menu(results)

    assert prompts == [("Choose what to view", ["Players", "Back"])]
