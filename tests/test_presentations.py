from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from speckit_delivery.core import run_demo, verify
from speckit_delivery.presentation import present
from speckit_delivery.storage import read


def test_editable_decks_notes_parity_and_links(project, authority):
    root, feature = project
    run_demo(root, feature, 1, github=authority)
    exported = present(root, feature, 1, github=authority)
    directory = Path(exported["directory"])
    data = read(directory / "content.json")
    for level in ("L0", "L1", "L2"):
        html = (directory / f"{level}.html").read_text()
        with ZipFile(directory / f"{level}.pptx") as pptx:
            slides = sorted(n for n in pptx.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            assert len(slides) == len(data["decks"][level])
            notes = [n for n in pptx.namelist() if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")]
            assert len(notes) == len(slides)
            text = " ".join(" ".join(ElementTree.fromstring(pptx.read(n)).itertext()) for n in slides)
            for slide in data["decks"][level]:
                assert slide["title"] in text
                assert slide["title"] in html
                for line in slide["body"]:
                    assert line in text
            assert "Execution evidence" in text
    report = verify(root, feature, 1, github=authority)
    assert report["status"] == "READY_FOR_REVIEW"
    (directory / "L0.pptx").write_bytes(b"tampered")
    assert verify(root, feature, 1, github=authority)["status"] == "BLOCKED"


def test_screenshot_export_and_browser_navigation(project, authority, server):
    from playwright.sync_api import sync_playwright
    from speckit_delivery.core import make_plan
    from speckit_delivery.storage import write

    root, feature = project
    mapping = read(root / "mapping.json")
    mapping["scenarios"].append(
        {
            "id": "ui",
            "kind": "ui",
            "title": "Save is visible",
            "obligations": ["AC-001"],
            "expected": "Clicking Save visibly changes the button to Saved.",
            "steps": [
                {"action": "goto", "target": server},
                {"action": "click", "target": "button"},
                {"action": "assert_text", "target": "button", "value": "Saved"},
            ],
        }
    )
    write(root / "mapping.json", mapping)
    make_plan(root, feature, root / "mapping.json")
    run_demo(root, feature, 1, github=authority)
    exported = present(root, feature, 1, github=authority)
    directory = Path(exported["directory"])
    with ZipFile(directory / "L1.pptx") as archive:
        assert any(n.startswith("ppt/media/") for n in archive.namelist())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto((directory / "L1.html").as_uri())
        assert page.locator("h1").first.inner_text() == "Greeting delivery"
        page.get_by_role("button", name="Next").click()
        assert page.evaluate("window.scrollY") > 0
        assert page.locator("img").evaluate_all("(imgs)=>imgs.every(i=>i.complete && i.naturalWidth>0)")
        browser.close()
