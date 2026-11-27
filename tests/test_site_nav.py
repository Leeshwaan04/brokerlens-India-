"""Unit tests for pipeline/site_nav.py (run: python3 -m unittest tests.test_site_nav)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import site_nav  # noqa: E402


def page(spa: bool, extra_head: str = "") -> str:
    """A minimal page shaped like the real shells: header with nav, icons and panels."""
    return (
        "<html><body><header class=\"site\"><div class=\"wrap nav\">"
        + site_nav.render_nav(spa)
        + site_nav.render_timings_button()
        + "<button class=\"icon-btn\" id=\"search-toggle\">s</button></div>"
        + site_nav.render_panels(spa)
        + "</header><main>content 100%</main></body></html>"
    )


class RenderTests(unittest.TestCase):
    def test_four_menus_in_order_one_direct_link_one_button(self):
        nav = site_nav.render_nav(False)
        self.assertEqual(re.findall(r'id="([a-z]+)-toggle"', nav), ["brokers", "markets", "tools", "learn"])
        self.assertEqual(nav.count('class="nav-paper-cta"'), 1)
        self.assertEqual(nav.count('data-nav="direct/ipo"'), 1)
        self.assertIn('aria-label="Main"', nav)
        self.assertNotIn("aria-haspopup", nav)

    def test_every_toggle_controls_a_panel_that_exists(self):
        html = page(False)
        for ctrl in re.findall(r'aria-controls="([a-z-]+)"', html):
            self.assertEqual(html.count(f'id="{ctrl}"'), 1, ctrl)

    def test_cta_opens_safely_with_campaign_tags(self):
        cta = re.search(r'<a href="([^"]+)" class="nav-paper-cta"([^>]*)>', site_nav.render_nav(False))
        self.assertTrue(cta.group(1).startswith("https://paper.brokerlens.in/?utm_source=brokerlens&amp;") or "&" in cta.group(1))
        self.assertIn('target="_blank"', cta.group(2))
        self.assertIn('rel="noopener"', cta.group(2))

    def test_data_link_only_on_known_spa_routes_and_only_for_the_spa(self):
        spa, static = site_nav.render_panels(True), site_nav.render_panels(False)
        self.assertNotIn("data-link", static)
        linked = set(re.findall(r'href="([^"]+)" data-link', spa))
        self.assertTrue(linked and linked <= site_nav._SPA_ROUTES, linked - site_nav._SPA_ROUTES)
        self.assertEqual(spa.replace(" data-link", ""), static)

    def test_every_old_header_destination_is_still_linked(self):
        old = ["/compare/", "/leaderboards/", "/calculators/", "/registry/", "/algo/", "/ipo/", "/news/",
               "/reports/state-of-indian-broking-2026/", "/brokers/", "/crypto/", "/coming-soon/us", "/coming-soon/gcc"]
        have = set(site_nav.all_internal_hrefs())
        self.assertEqual([h for h in old if h not in have], [])

    def test_no_percent_in_nav_markup(self):
        # The page templates are %-formatted later; _fill_nav escapes, but nothing should need it.
        self.assertNotIn("%", site_nav.render_nav(False) + site_nav.render_panels(False))

    def test_flat_nav_has_the_same_labels_and_the_button(self):
        flat = site_nav.render_flat_nav()
        for label in ["Brokers", "Compare", "Markets", "IPO", "Tools", "Learn", "Practise free"]:
            self.assertIn(f">{label}</a>", flat)

    def test_labels_are_escaped(self):
        self.assertNotIn("<script", site_nav.render_panels(False))


class UpgradeTests(unittest.TestCase):
    def test_idempotent(self):
        once = site_nav.upgrade_header_html(page(False))
        self.assertEqual(site_nav.upgrade_header_html(once), once)

    def test_rerenders_so_later_nav_changes_reach_committed_pages(self):
        stale = page(False).replace('class="nav-paper-cta"', 'class="nav-paper-cta old-class"').replace("Learn <", "Read <")
        fresh = site_nav.upgrade_header_html(stale)
        self.assertNotIn("old-class", fresh)
        self.assertIn("Learn <", fresh)

    def test_no_duplicate_timings_button(self):
        out = site_nav.upgrade_header_html(page(False))
        self.assertEqual(out.count('id="timings-toggle"'), 1)
        self.assertEqual(out.count('id="mega-timings"'), 1)
        self.assertEqual(out.count('id="search-toggle"'), 1)

    def test_old_header_is_moved_to_the_new_one(self):
        old = (
            '<header class="site"><div class="wrap nav"><nav class="nav-links" id="navlinks">'
            '<button class="mega-toggle" id="markets-toggle" aria-expanded="false" aria-controls="mega-markets">Brokers <span>v</span></button>'
            '<a href="/compare/" data-link>Compare</a></nav>'
            '<button class="icon-btn" id="search-toggle">s</button></div>'
            '<div class="mega" id="mega-timings" hidden></div><div class="mega" id="mega-markets" hidden></div></header>'
        )
        self.assertTrue(site_nav.still_on_old_header(old))
        new = site_nav.upgrade_header_html(old)
        self.assertFalse(site_nav.still_on_old_header(new))
        self.assertIn('id="brokers-toggle"', new)
        self.assertIn('data-link', new)            # a page that was on the SPA router stays on it
        self.assertEqual(new.count('id="mega-timings"'), 1)

    def test_spa_flag_survives_a_second_upgrade(self):
        spa_once = site_nav.upgrade_header_html(page(True))
        self.assertIn("data-link", spa_once)
        self.assertIn("data-link", site_nav.upgrade_header_html(spa_once))

    def test_half_upgrade_is_refused(self):
        broken = page(False).replace('<button class="icon-btn" id="search-toggle">s</button>', "")
        self.assertEqual(site_nav.upgrade_header_html(broken), broken)

    def test_pages_without_the_full_header_are_untouched(self):
        for html in ["<html><body>no header</body></html>",
                     "<header>" + site_nav.render_flat_nav() + "</header>",
                     '<header><nav class="nav" style="display:flex"><a href="/">x</a></nav></header>']:
            self.assertEqual(site_nav.upgrade_header_html(html), html)

    def test_page_content_is_preserved(self):
        out = site_nav.upgrade_header_html(page(False))
        self.assertIn("<main>content 100%</main>", out)


if __name__ == "__main__":
    unittest.main()
