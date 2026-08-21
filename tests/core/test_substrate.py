"""Honest contract tests for telos/core/project/substrate.py (Project, ProjectPortfolio)."""

from telos.core.project.substrate import Project, ProjectPortfolio, ProjectLifecycle, NotebookEntry


def test_project_defaults_to_birth_lifecycle():
    p = Project(id="p1", name="Alpha", mission_id="m1")
    assert p.lifecycle == ProjectLifecycle.BIRTH
    assert p.is_active is False
    assert p.value == 0.5
    assert p.notebooks == []


def test_age_cycles_is_nonnegative():
    p = Project(id="p1", name="Alpha", mission_id="m1", birth_cycle=10, last_active_cycle=3)
    assert p.age_cycles == 0
    p.last_active_cycle = 15
    assert p.age_cycles == 5


def test_add_note_appends_notebook_entry():
    p = Project(id="p1", name="Alpha", mission_id="m1")
    p.add_note(3, "some content", entry_type="hypothesis")
    assert len(p.notebooks) == 1
    e = p.notebooks[0]
    assert isinstance(e, NotebookEntry)
    assert e.cycle == 3
    assert e.content == "some content"
    assert e.entry_type == "hypothesis"


def test_add_note_defaults_to_reflection():
    p = Project(id="p1", name="Alpha", mission_id="m1")
    p.add_note(1, "a note")
    assert p.notebooks[0].entry_type == "reflection"


def test_set_cognitive_context_wires_pipeline_attributes():
    p = Project(id="p1", name="Alpha", mission_id="m1")
    pipeline = type("P", (), {
        "_curiosity_drive": "CD",
        "_theory_builder": "TB",
        "_unknown_unknown_detector": "UU",
        "_model_competition": "MC",
        "_regret_memory": "RM",
    })()
    p.set_cognitive_context(pipeline)
    assert p.curiosity_drive == "CD"
    assert p.theory_builder == "TB"
    assert p.unknown_unknown_detector == "UU"
    assert p.model_competition == "MC"
    assert p.regret_memory == "RM"


def test_set_cognitive_context_handles_missing_attributes():
    p = Project(id="p1", name="Alpha", mission_id="m1")
    p.set_cognitive_context(object())
    assert p.curiosity_drive is None
    assert p.theory_builder is None


def test_project_to_dict():
    p = Project(id="p1", name="Alpha", mission_id="m1",
                lifecycle=ProjectLifecycle.ACTIVE, birth_cycle=0, last_active_cycle=5)
    p.add_note(5, "hi", entry_type="insight")
    d = p.to_dict()
    assert d["id"] == "p1"
    assert d["name"] == "Alpha"
    assert d["mission_id"] == "m1"
    assert d["lifecycle"] == "active"
    assert d["value"] == 0.5
    assert d["age_cycles"] == 5
    assert d["notebook_entries"] == 1


def test_portfolio_create_project_sets_active_when_first():
    pf = ProjectPortfolio()
    p = pf.create_project("proj1", "Mission One", "mission1", cycle=0)
    assert pf._active_project_id == "proj1"
    assert pf.active_project is None  # birth lifecycle, not ACTIVE
    assert p.lifecycle == ProjectLifecycle.BIRTH


def test_portfolio_activate_sets_active():
    pf = ProjectPortfolio()
    pf.create_project("proj1", "Alpha", "mission1", cycle=0)
    assert pf.activate("proj1", cycle=5) is True
    assert pf.active_project is not None
    assert pf.active_project.id == "proj1"
    assert pf.active_project.is_active


def test_portfolio_activate_returns_false_for_unknown():
    pf = ProjectPortfolio()
    assert pf.activate("missing", cycle=0) is False


def test_portfolio_activate_returns_false_for_archived():
    pf = ProjectPortfolio()
    pf.create_project("proj1", "Alpha", "mission1", cycle=0)
    pf.activate("proj1", cycle=1)
    pf.set_lifecycle("proj1", ProjectLifecycle.ARCHIVED, cycle=2)
    assert pf.activate("proj1", cycle=3) is False
    assert len(pf.active_projects) == 0


def test_portfolio_set_lifecycle_updates_last_active():
    pf = ProjectPortfolio()
    p = pf.create_project("proj1", "Alpha", "mission1", cycle=0)
    pf.set_lifecycle("proj1", ProjectLifecycle.ACTIVE, cycle=9)
    assert p.lifecycle == ProjectLifecycle.ACTIVE
    assert p.last_active_cycle == 9


def test_portfolio_set_lifecycle_returns_false_for_unknown():
    pf = ProjectPortfolio()
    assert pf.set_lifecycle("missing", ProjectLifecycle.ACTIVE, cycle=0) is False


def test_portfolio_active_projects_lists_only_active():
    pf = ProjectPortfolio()
    pf.create_project("a", "Alpha", "m1", cycle=0)
    pf.create_project("b", "Beta", "m1", cycle=0)
    pf.activate("b", cycle=1)
    ids = sorted(p.id for p in pf.active_projects)
    assert ids == ["b"]


def test_portfolio_project_count_and_to_dict():
    pf = ProjectPortfolio()
    pf.create_project("a", "Alpha", "m1", cycle=0)
    pf.create_project("b", "Beta", "m1", cycle=0)
    pf.activate("a", cycle=1)
    d = pf.to_dict()
    assert d["total_projects"] == 2
    assert d["active_projects"] == 1
    assert d["active_project_id"] == "a"
    assert set(d["projects"]) == {"a", "b"}
