import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import unittest
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest import mock

import run as reminder_run
from feishu_notify import FeishuNotificationError, FeishuNotifier, feishu_signature


class StaticFileSecurityTests(unittest.TestCase):
    def test_private_hidden_and_non_asset_files_are_not_served(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text("ok")
            (root / "private").mkdir()
            (root / "private" / "token").write_text("secret")
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: main")
            (root / "run.py").write_text("backend")
            with mock.patch.object(reminder_run, "APP_DIRECTORY", root):
                server = reminder_run.ReminderServer(("127.0.0.1", 0), reminder_run.ReminderHandler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    for method in ("GET", "HEAD"):
                        for path in ("/private/token", "/.git/HEAD", "/%2egit/HEAD", "/run.py", "/private/"):
                            with self.subTest(method=method, path=path):
                                with self.assertRaises(urllib.error.HTTPError) as caught:
                                    urllib.request.urlopen(urllib.request.Request(base + path, method=method))
                                self.assertEqual(caught.exception.code, 404)
                    with urllib.request.urlopen(base + "/") as response:
                        self.assertEqual(response.read(), b"ok")
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join(timeout=2)


class FeishuNotifierTests(unittest.TestCase):
    def test_signature_matches_feishu_hmac_contract(self):
        timestamp = 1599360473
        expected = __import__("base64").b64encode(
            __import__("hmac").new(
                f"{timestamp}\ntest-secret".encode("utf-8"),
                digestmod=__import__("hashlib").sha256,
            ).digest()
        ).decode("ascii")
        self.assertEqual(feishu_signature("test-secret", timestamp), expected)

    def test_settings_are_private_and_outbox_is_deduplicated_and_persistent(self):
        with tempfile.TemporaryDirectory() as temporary:
            delivered = []
            notifier = FeishuNotifier(
                data_directory=Path(temporary),
                transport=lambda webhook, secret, payload: delivered.append((webhook, secret, payload)),
            )
            status = notifier.update_settings(
                {
                    "enabled": True,
                    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                    "secret": "private-secret",
                    "events": {"codex_completed": True, "work_ended": False},
                }
            )
            self.assertTrue(status["configured"])
            self.assertTrue(status["hasSecret"])
            self.assertNotIn("webhook", status)
            self.assertNotIn("secret", status)
            self.assertEqual(notifier.config_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(notifier.database_path.stat().st_mode & 0o777, 0o600)

            accepted = notifier.enqueue(
                "codex:thread:turn",
                "codex_completed",
                {"cardTitle": "任务 A", "completionCount": 3},
            )
            duplicate = notifier.enqueue(
                "codex:thread:turn",
                "codex_completed",
                {"cardTitle": "任务 A", "completionCount": 3},
            )
            disabled_event = notifier.enqueue(
                "work-ended:1", "work_ended", {"completionCount": 3}
            )
            self.assertTrue(accepted["accepted"])
            self.assertEqual(duplicate["reason"], "duplicate")
            self.assertEqual(disabled_event["reason"], "event_disabled")

            notifier._deliver(notifier._next_pending())
            self.assertEqual(len(delivered), 1)
            self.assertEqual(delivered[0][1], "private-secret")
            self.assertEqual(delivered[0][2]["msg_type"], "post")
            self.assertEqual(notifier.status()["pending"], 0)

            disabled = notifier.update_settings({"enabled": False})
            self.assertFalse(disabled["enabled"])
            self.assertTrue(disabled["configured"])
            self.assertTrue(disabled["hasSecret"])
            reenabled = notifier.update_settings({"enabled": True})
            self.assertTrue(reenabled["enabled"])
            self.assertTrue(reenabled["configured"])
            self.assertTrue(reenabled["hasSecret"])

            restarted = FeishuNotifier(data_directory=Path(temporary), transport=lambda *_: None)
            self.assertTrue(restarted.status()["enabled"])
            self.assertEqual(restarted.status()["pending"], 0)

    def test_retry_survives_failure_and_disable_cancels_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = [1000.0]

            def fail(*_args):
                raise FeishuNotificationError("临时断网")

            notifier = FeishuNotifier(
                data_directory=Path(temporary), transport=fail, clock=lambda: now[0]
            )
            notifier.update_settings(
                {
                    "enabled": True,
                    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                }
            )
            notifier.enqueue("event-1", "codex_completed", {"cardTitle": "测试"})
            notifier._deliver(notifier._next_pending())
            with notifier._connect() as connection:
                row = connection.execute(
                    "SELECT status, attempts, next_attempt, last_error FROM notifications"
                ).fetchone()
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["attempts"], 1)
            self.assertEqual(row["next_attempt"], 1005.0)
            self.assertIn("临时断网", row["last_error"])

            notifier.update_settings({"enabled": False})
            with notifier._connect() as connection:
                status = connection.execute(
                    "SELECT status FROM notifications"
                ).fetchone()[0]
            self.assertEqual(status, "cancelled")

    def test_frontend_and_handler_keep_secret_server_side(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")
        server = (project_root / "run.py").read_text(encoding="utf-8")
        self.assertIn('id="feishuDialog"', html)
        self.assertIn('id="feishuSettingsButton"', html)
        self.assertIn('id="feishuQuickEnabled"', html)
        self.assertIn('type="password"', html)
        self.assertIn('"X-Lumen-Request": "1"', app)
        self.assertIn('feishuRequest("/api/feishu/settings", { enabled: desiredEnabled })', app)
        self.assertIn('enqueueFeishuEvent("codex_completed"', app)
        self.assertIn('enqueueFeishuEvent("work_ended"', app)
        self.assertIn('if parsed.path == "/api/feishu/events":', server)
        self.assertNotIn("localStorage.setItem(FEISHU", app)


class HeaderClockFirstPaintTests(unittest.TestCase):
    @staticmethod
    def _bern_snapshots(*timestamps):
        project_root = Path(__file__).parent
        script = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync(process.argv[1], "utf8");
source = source.slice(0, source.indexOf("function corpusClockOffsetSeconds"));
const document = {
  querySelector: () => null,
  getElementById: () => null,
  createElementNS: () => ({ setAttribute() {}, classList: { add() {} } }),
};
const window = { location: { search: "" }, matchMedia: () => ({ matches: false }) };
const context = {
  console, Date, Intl, Math, Number, String, Object, Array, Map, Set, JSON,
  URLSearchParams,
  localStorage: { getItem: () => null, setItem() {} },
  document, window,
  performance: { now: () => 0 },
  requestAnimationFrame: () => 0,
};
vm.createContext(context);
vm.runInContext(source, context);
const snapshot = context.window.__bernZytgloggeClockSnapshot;
console.log(JSON.stringify(JSON.parse(process.argv[2]).map((value) => snapshot(value))));
"""
        result = subprocess.run(
            [
                "node",
                "-e",
                script,
                str(project_root / "app.js"),
                json.dumps(timestamps),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_header_clock_stays_hidden_until_saved_skin_hydrates(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        css = (project_root / "styles.css").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-clock-ready="false"', html)
        self.assertRegex(
            css,
            r'\.header-clock\[data-clock-ready="false"\]\s*\{[^}]*visibility:\s*hidden',
        )
        self.assertRegex(
            css,
            r'\.header-clock\[data-clock-ready="false"\]\s+\.clock-skin\s*\{[^}]*transition:\s*none',
        )
        self.assertIn("function revealHeaderClockAfterHydration()", app)
        self.assertLess(
            app.rindex("ensureDailyHeaderClock(true);"),
            app.rindex("revealHeaderClockAfterHydration();"),
        )

    def test_four_clock_registry_matches_four_svg_skins(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")

        for clock_id in ("corpus", "big-ben", "prague-orloj", "bern-zytglogge"):
            self.assertIn(f'data-clock-id="{clock_id}"', html)
            self.assertIn(f'id: "{clock_id}"', app)
        self.assertIn("const HEADER_CLOCK_RUNTIMES = {", app)
        self.assertIn('"prague-orloj": {', app)
        self.assertIn('"bern-zytglogge": {', app)
        self.assertIn("HEADER_CLOCKS.forEach((clock) => HEADER_CLOCK_RUNTIMES", app)

    def test_bern_zytglogge_exposes_complete_beijing_clock_snapshot(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")

        for element_id in (
            "bernZytgloggeClock",
            "bernZytgloggeClockTime",
            "bernZytgloggeMainHourHand",
            "bernZytgloggeMainMinuteHand",
            "bernZytgloggeAstrolabeZodiac",
            "bernZytgloggeSunHand",
            "bernZytgloggeSunSymbol",
            "bernZytgloggeMoonSymbol",
            "bernZytgloggeMoonLight",
            "bernZytgloggeCalendarDisk",
            "bernZytgloggeBearParade",
            "bernZytgloggeJesterArm",
            "bernZytgloggeRooster",
            "bernZytgloggeChronosArm",
            "bernZytgloggeChronosHourglass",
            "bernZytgloggeJacquemartArm",
            "bernZytgloggeBell",
        ):
            self.assertIn(f'id="{element_id}"', html)
            self.assertIn(f'querySelector("#{element_id}")', app)

        self.assertIn("function bernZytgloggeClockState", app)
        self.assertIn("function bernZytgloggeAutomatonState", app)
        self.assertIn("const displayTime = displayTimeParts(date);", app)
        self.assertIn("bernZytgloggeAutomatonState(displayTime)", app)
        self.assertIn("BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS = 210", app)
        self.assertIn("BERN_ZYTGLOGGE_SIDEREAL_RATE = 1.00273790935", app)
        self.assertIn("BERN_ZYTGLOGGE_LONGITUDE = 7.4474", app)
        self.assertIn("BERN_ZYTGLOGGE_CENTER = Object.freeze({ x: 350, y: 820 })", app)
        self.assertIn("BERN_ZYTGLOGGE_ZODIAC_CENTER_OFFSET = Object.freeze({ x: 0, y: -38 })", app)
        self.assertIn("BERN_ZYTGLOGGE_ZODIAC_OUTER_RADIUS = 151", app)
        self.assertIn("function bernZytgloggeLocalSiderealHours", app)
        self.assertIn("360.98564736629 * daysSinceJ2000", app)
        self.assertIn("(julianCenturies * julianCenturies * julianCenturies) / 38710000", app)
        self.assertIn("const sunAngle = positiveModulo((decimalHour - 12) * 15, 360);", app)
        self.assertIn("const zodiacAngle = positiveModulo(siderealHours * 15, 360);", app)
        self.assertIn("const moonAngle = positiveModulo(sunAngle - lunarElongation, 360);", app)
        self.assertIn("calendarAngle: zodiacAngle", app)
        self.assertIn("sunRadius,", app)
        self.assertIn("zodiacCenter,", app)
        self.assertRegex(
            app,
            r"displayTime\.minute > 0 && displayTime\.minute % 15 === 0",
        )
        self.assertIn('timeZone: DISPLAY_TIME_ZONE', app)
        self.assertIn('"__bernZytgloggeClockSnapshot"', app)

        for phase in (
            "opening-rooster",
            "bear-parade",
            "jester",
            "quarter-bells",
            "chronos",
            "hans-strikes",
            "final-rooster",
        ):
            self.assertIn(f'"{phase}"', app)

        for variable in (
            "--zyt-main-hour-angle",
            "--zyt-main-hour-counter-angle",
            "--zyt-main-minute-angle",
            "--zyt-sun-angle",
            "--zyt-zodiac-angle",
            "--zyt-moon-angle",
            "--zyt-calendar-angle",
            "--zyt-rooster-pulse",
            "--zyt-bear-parade",
            "--zyt-jester-angle",
            "--zyt-jester-left-angle",
            "--zyt-jester-right-angle",
            "--zyt-quarter-pulse",
            "--zyt-chronos-angle",
            "--zyt-hourglass-angle",
            "--zyt-jacquemart-angle",
            "--zyt-bell-pulse",
        ):
            self.assertIn(variable, app)

        for dataset in (
            "mainHourCounterAngle",
            "sunRadius",
            "zodiacCenterX",
            "zodiacCenterY",
            "quarterPulse",
            "bellPulse",
            "jesterLeftAngle",
            "jesterRightAngle",
            "hourglassAngle",
        ):
            self.assertIn(f"dataset.{dataset}", app)

    def test_bern_zytglogge_facade_matches_reference_proportions(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        css = (project_root / "styles.css").read_text(encoding="utf-8")

        def layout_transform(class_name):
            match = re.search(
                rf'class="{class_name}"\s+transform="translate\(([-\d.]+) ([-\d.]+)\) scale\(([-\d.]+)\)"',
                html,
            )
            self.assertIsNotNone(match, class_name)
            return tuple(float(value) for value in match.groups())

        upper_x, upper_y, upper_scale = layout_transform("zyt-layout-upper")
        planets_x, planets_y, planets_scale = layout_transform("zyt-layout-planets")
        astro_x, astro_y, astro_scale = layout_transform("zyt-layout-astrolabe")
        automata_x, automata_y, automata_scale = layout_transform("zyt-layout-automata")

        def transformed_box(box, transform):
            left, top, right, bottom = box
            tx, ty, scale = transform
            return (
                left * scale + tx,
                top * scale + ty,
                right * scale + tx,
                bottom * scale + ty,
            )

        upper = transformed_box((348 - 262, 306 - 262, 348 + 262, 306 + 262), (upper_x, upper_y, upper_scale))
        lower = transformed_box((350 - 287, 820 - 287, 350 + 287, 820 + 287), (astro_x, astro_y, astro_scale))
        planets = transformed_box((92, 536, 611, 619), (planets_x, planets_y, planets_scale))
        automata = transformed_box((641, 174, 978, 1126), (automata_x, automata_y, automata_scale))

        upper_diameter = upper[2] - upper[0]
        lower_diameter = lower[2] - lower[0]
        upper_center_y = (upper[1] + upper[3]) / 2
        lower_center_y = (lower[1] + lower[3]) / 2
        automata_width = automata[2] - automata[0]
        automata_height = automata[3] - automata[1]

        self.assertGreaterEqual(upper_diameter / lower_diameter, 1.17)
        self.assertLessEqual(upper_diameter / lower_diameter, 1.30)
        self.assertGreaterEqual((lower_center_y - upper_center_y) / lower_diameter, 1.45)
        self.assertLessEqual((lower_center_y - upper_center_y) / lower_diameter, 1.60)
        # At the delivered 160px size, even a mathematically small overlap
        # merges the pavilion figures with the astronomical dial. Keep a
        # visible architectural joint between the two components.
        self.assertGreaterEqual(automata[0] - lower[2], lower_diameter * 0.025)
        self.assertLessEqual(automata[0] - lower[2], lower_diameter * 0.08)
        self.assertGreaterEqual(automata[1] - upper[3], lower_diameter * 0.04)
        self.assertLessEqual(automata[1] - upper[3], lower_diameter * 0.08)
        self.assertGreaterEqual(lower[1] - automata[1], 0)
        self.assertGreaterEqual(lower[1] - automata[1], lower_diameter * 0.25)
        self.assertLessEqual(lower[1] - automata[1], lower_diameter * 0.40)
        self.assertLessEqual(abs(automata[3] - lower[3]), lower_diameter * 0.05)
        self.assertGreaterEqual(automata_width / lower_diameter, 0.44)
        self.assertLessEqual(automata_width / lower_diameter, 0.52)
        self.assertGreaterEqual(automata_height / lower_diameter, 1.30)
        self.assertLessEqual(automata_height / lower_diameter, 1.45)
        self.assertLessEqual(automata[3], 1240 - 30)
        self.assertLessEqual(abs(planets[0] - lower[0]), lower_diameter * 0.03)
        self.assertLessEqual(abs(planets[2] - lower[2]), lower_diameter * 0.03)
        self.assertLessEqual(lower[1] - planets[3], lower_diameter * 0.04)
        self.assertGreaterEqual(planets[1] - upper[3], 20)

        for detail_class in (
            "zyt-facade-background",
            "zyt-facade-depth",
            "zyt-masonry-joints",
            "zyt-plaster-patina",
            "zyt-upper-stucco",
            "zyt-lower-bay",
            "zyt-facade-cornice",
            "zyt-upper-garland",
            "zyt-upper-crest",
            "zyt-facade-quoins",
            "zyt-upper-windows",
            "zyt-lower-pilasters",
        ):
            self.assertIn(f'class="{detail_class}"', html)
        for gradient_id in (
            "bernZytgloggeMasonryWall",
            "bernZytgloggeUpperPlaster",
            "bernZytgloggeLowerPanel",
        ):
            self.assertIn(f'id="{gradient_id}"', html)
        self.assertIn('class="zyt-facade" x="78" y="-48" width="868" height="1288" rx="52"', html)
        self.assertIn('class="zyt-upper-stucco" x="78" y="-48" width="868" height="678"', html)
        self.assertIn('class="zyt-lower-bay" d="M148 646H650V1240H148Z"', html)
        self.assertIn('viewBox="0 -48 1024 1288"', html)
        self.assertIn('id="bernZytgloggeFacadeClip"', html)
        self.assertIn('rx="52"', html)
        self.assertIn('clip-path="url(#bernZytgloggeFacadeClip)"', html)
        self.assertEqual(html.count('class="zyt-upper-quoin"'), 22)
        self.assertIn('<rect x="380" y="-44" width="44" height="20" rx="4" />', html)
        self.assertIn('<rect x="600" y="-44" width="44" height="20" rx="4" />', html)
        window_sill_visual_bottom = -18 + 1.5
        self.assertGreaterEqual(upper[1] - window_sill_visual_bottom, 20)
        self.assertRegex(css, r"\.zyt-layout-hans\s*\{[^}]*opacity:\s*0")
        self.assertRegex(css, r"\.zyt-facade-shadow\s*\{[^}]*display:\s*none")
        self.assertRegex(css, r"\.zyt-facade\s*\{[^}]*stroke:\s*none")
        self.assertRegex(css, r"\.zyt-upper-quoin\s*\{[^}]*fill:")
        self.assertIsNotNone(
            re.search(
                r"@media\s*\(max-width:\s*720px\).*?\.clock-skin--bern-zytglogge\s+\.zyt-clock-art\s*\{[^}]*transform:\s*scale\(1\.06\)",
                css,
                re.DOTALL,
            )
        )
        mobile_switch = re.search(
            r"@media\s*\(max-width:\s*720px\)(.*?)(?=@media|\Z)",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile_switch)
        self.assertRegex(
            mobile_switch.group(1),
            r"\.clock-skin-switch\s+svg\s*\{[^}]*right:\s*-6px[^}]*width:\s*8px[^}]*height:\s*8px",
        )

        automata_markup = re.search(
            r'<g class="zyt-layout-automata"[^>]*>(.*?)</g>\s*</g>\s*</g>\s*</svg>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(automata_markup)
        for element_id in (
            "bernZytgloggeJesterArm",
            "bernZytgloggeRooster",
            "bernZytgloggeChronosArm",
            "bernZytgloggeLion",
            "bernZytgloggeBearParade",
        ):
            self.assertIn(f'id="{element_id}"', automata_markup.group(1))
        self.assertIn('clip-path="url(#bernZytgloggeBearWindowClip)"', automata_markup.group(1))

    def test_bern_zytglogge_astronomy_and_automata_invariants(self):
        (
            sidereal_start,
            sidereal_next,
            jester,
            hour_quarter,
            regular_quarter,
            chronos,
            hans,
            final_rooster,
            waiting,
        ) = self._bern_snapshots(
            "2026-08-25T04:00:00.000Z",
            "2026-08-25T04:01:00.000Z",
            "2026-08-25T15:58:30.000Z",
            "2026-08-25T16:00:02.000Z",
            "2026-08-25T16:15:01.000Z",
            "2026-08-25T16:00:09.000Z",
            "2026-08-25T16:00:25.000Z",
            "2026-08-25T16:00:35.000Z",
            "2026-08-25T16:00:45.000Z",
        )

        zodiac_delta = (sidereal_next["zodiacAngle"] - sidereal_start["zodiacAngle"]) % 360
        self.assertGreater(zodiac_delta, 0)
        self.assertLess(zodiac_delta, 1)
        for state in (sidereal_start, sidereal_next):
            self.assertAlmostEqual(state["calendarAngle"], state["zodiacAngle"], places=9)
            self.assertAlmostEqual(
                state["mainHourCounterAngle"],
                -state["mainHourAngle"],
                places=9,
            )
            self.assertGreaterEqual(state["sunRadius"], 151 - 38)
            self.assertLessEqual(state["sunRadius"], 151 + 38)
            center = state["zodiacCenter"]
            center_offset = ((center["x"] - 350) ** 2 + (center["y"] - 820) ** 2) ** 0.5
            self.assertAlmostEqual(center_offset, 38, places=6)

        self.assertNotEqual(jester["automaton"]["jesterLeftAngle"], 0)
        self.assertAlmostEqual(
            jester["automaton"]["jesterLeftAngle"],
            -jester["automaton"]["jesterRightAngle"],
            places=9,
        )
        for quarter in (hour_quarter, regular_quarter):
            self.assertEqual(quarter["automaton"]["phase"], "quarter-bells")
            self.assertGreater(quarter["automaton"]["quarterPulse"], 0)
            self.assertEqual(quarter["automaton"]["bellPulse"], 0)

        self.assertEqual(chronos["automaton"]["phase"], "chronos")
        self.assertGreater(chronos["automaton"]["hourglassAngle"], 0)
        self.assertLess(chronos["automaton"]["hourglassAngle"], 180)
        self.assertEqual(hans["automaton"]["phase"], "hans-strikes")
        self.assertAlmostEqual(hans["automaton"]["hourglassAngle"], 180, places=9)
        self.assertGreater(hans["automaton"]["bellPulse"], 0)
        self.assertEqual(hans["automaton"]["quarterPulse"], 0)
        self.assertEqual(final_rooster["automaton"]["phase"], "final-rooster")
        self.assertGreater(final_rooster["automaton"]["hourglassAngle"], 0)
        self.assertLess(final_rooster["automaton"]["hourglassAngle"], 180)
        self.assertEqual(waiting["automaton"]["phase"], "waiting")
        self.assertEqual(waiting["automaton"]["hourglassAngle"], 0)
        self.assertEqual(waiting["automaton"]["chronosAngle"], 0)

    def test_bern_zytglogge_resume_resets_every_unwrapped_mechanism(self):
        app = (Path(__file__).parent / "app.js").read_text(encoding="utf-8")

        self.assertIn('classList.add("is-mechanism-syncing")', app)
        self.assertIn('classList.remove("is-mechanism-syncing")', app)
        for display_angle, state_angle in (
            ("bernZytgloggeMainHourAngle", "state.mainHourAngle"),
            ("bernZytgloggeMainMinuteAngle", "state.mainMinuteAngle"),
            ("bernZytgloggeSunAngle", "state.sunAngle"),
            ("bernZytgloggeZodiacAngle", "state.zodiacAngle"),
            ("bernZytgloggeMoonAngle", "state.moonAngle"),
            ("bernZytgloggeCalendarAngle", "state.calendarAngle"),
        ):
            self.assertRegex(
                app,
                rf"function syncActiveBernZytgloggeClock[\s\S]*?{display_angle} = null;",
            )
            self.assertIn(f"{display_angle} = unwrapClockAngle(", app)
            self.assertIn(state_angle, app)

        self.assertRegex(
            app,
            r'"bern-zytglogge": \{[\s\S]*?'
            r"resume: \(\{ date \}\) => syncActiveBernZytgloggeClock\(date\)",
        )
        self.assertRegex(
            app,
            r"const automaton = reduceMotion[\s\S]*?"
            r"roosterPulse: 0,[\s\S]*?bellPulse: 0,",
        )
        bern_update = app[
            app.index("function updateBernZytgloggeClock"):
            app.index("function initializeBernZytgloggeClock")
        ]
        for frozen_action in (
            "roosterPulse: 0",
            "bearParade: 0",
            "jesterLeftAngle: 0",
            "jesterRightAngle: 0",
            "quarterPulse: 0",
            "chronosAngle: 0",
            "hourglassAngle: 0",
            "jacquemartAngle: 0",
            "bellPulse: 0",
        ):
            self.assertIn(frozen_action, bern_update)
        self.assertIn("`${(-bernZytgloggeMainHourAngle).toFixed(6)}deg`", bern_update)
        self.assertIn(
            "`translate(${BERN_ZYTGLOGGE_CENTER.x.toFixed(3)} ${sunSymbolY.toFixed(3)})`",
            bern_update,
        )
        self.assertIn("zodiacCenter: Object.freeze({ ...state.zodiacCenter })", app)

    def test_prague_orloj_exposes_reproducible_astronomical_snapshot(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="pragueOrlojOldCzechRing"', html)
        self.assertIn('id="pragueOrlojZodiac"', html)
        self.assertIn('id="pragueOrlojSunSymbol"', html)
        self.assertIn('id="pragueOrlojMoonLight"', html)
        self.assertIn("function pragueOrlojClockState", app)
        self.assertIn("PRAGUE_ORLOJ_SYNODIC_MONTH_DAYS = 29.5322986", app)
        self.assertIn("const cet = pragueOrlojCETParts(quantizedDate);", app)
        self.assertIn("const mechanicalSunAngle = positiveModulo", app)
        self.assertIn("pragueOrlojAutomatonState(displayTime)", app)
        self.assertRegex(
            app,
            r"if \(waxing\) \{\s*outer\.push\(\{ x: edge, y \}\)",
        )
        self.assertRegex(
            app,
            r"\} else \{\s*outer\.push\(\{ x: -edge, y \}\)",
        )
        self.assertIn('"__pragueOrlojClockSnapshot"', app)

    def test_prague_lower_figures_keep_upper_figure_detail_parity(self):
        project_root = Path(__file__).parent
        html = (project_root / "index.html").read_text(encoding="utf-8")
        css = (project_root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="pragueOrlojWoodReliefLower"', html)
        self.assertIn('class="orloj-calendar-figure-plinths"', html)
        for figure_class in (
            "orloj-philosopher",
            "orloj-archangel",
            "orloj-astronomer",
            "orloj-chronicler",
        ):
            self.assertIn(figure_class, html)
        for signature_detail in (
            "wood-feather",
            "wood-shield-cross",
            "wood-telescope-barrel",
            "wood-book-pages",
        ):
            self.assertIn(signature_detail, html)
            self.assertIn(signature_detail, css)
        self.assertRegex(
            css,
            r"\.orloj-calendar-figures\s*\{[^}]*"
            r"filter:\s*url\(#pragueOrlojWoodReliefLower\)",
        )

    def test_all_readable_clocks_use_beijing_time_explicitly(self):
        root = Path(__file__).parent
        app = (root / "app.js").read_text(encoding="utf-8")
        html = (root / "index.html").read_text(encoding="utf-8")

        self.assertIn('const DISPLAY_TIME_ZONE = "Asia/Shanghai";', app)
        self.assertGreaterEqual(app.count("timeZone: DISPLAY_TIME_ZONE"), 6)
        self.assertIn("function displayTimeParts", app)
        self.assertRegex(
            app,
            r"function corpusClockState\(date = new Date\(\)\) \{\s*"
            r"const displayTime = displayTimeParts\(date\);",
        )
        self.assertIn("const beatDisplayTime = displayTimeParts(beatDate);", app)
        self.assertIn("bigBenChimeState(date, displayTime)", app)
        self.assertIn("const quantizedDisplayTime = displayTimeParts(quantizedDate);", app)
        self.assertIn("pragueOrlojAutomatonState(displayTime)", app)
        self.assertRegex(
            app,
            r"function bernZytgloggeClockState\(value = new Date\(\)\)[\s\S]*?"
            r"const displayTime = displayTimeParts\(date\);",
        )
        self.assertIn("bernZytgloggeAutomatonState(displayTime)", app)
        self.assertIn("北京时间", html)
        self.assertNotIn("金手显示固定中欧时间", html)

    def test_prague_orloj_unwraps_rotating_parts_across_zero_degrees(self):
        app = (Path(__file__).parent / "app.js").read_text(encoding="utf-8")

        for display_angle, state_angle in (
            ("pragueOrlojSunAngle", "state.sunAngle"),
            ("pragueOrlojZodiacAngle", "state.zodiacAngle"),
            ("pragueOrlojMoonAngle", "state.moonAngle"),
            ("pragueOrlojOldCzechAngle", "state.oldCzechRingAngle"),
            ("pragueOrlojCalendarAngle", "state.calendarAngle"),
        ):
            self.assertIn(
                f"{display_angle} = unwrapClockAngle(",
                app,
            )
            self.assertIn(state_angle, app)
            self.assertRegex(
                app,
                rf"function syncActivePragueOrlojClock[\s\S]*?{display_angle} = null;",
            )

    def test_prague_orloj_dials_keep_reference_photo_proportions(self):
        css = (Path(__file__).parent / "styles.css").read_text(encoding="utf-8")

        upper = re.search(
            r"\.orloj-upper-mechanism\s*\{[^}]*"
            r"translateY\((-?[\d.]+)px\)\s+scale\(([\d.]+)\)",
            css,
            re.S,
        )
        calendar = re.search(
            r"\.orloj-calendar-assembly\s*\{[^}]*"
            r"translateY\((-?[\d.]+)px\)\s+scale\(([\d.]+)\)",
            css,
            re.S,
        )
        calendar_core = re.search(
            r"\.orloj-calendar-disk\s*\{[^}]*scale\(([\d.]+)\)",
            css,
            re.S,
        )
        self.assertIsNotNone(upper)
        self.assertIsNotNone(calendar)
        self.assertIsNotNone(calendar_core)

        upper_translate, upper_scale = map(float, upper.groups())
        calendar_translate, calendar_scale = map(float, calendar.groups())
        core_scale = float(calendar_core.group(1))
        upper_radius = 371 * upper_scale
        calendar_radius = 118 * calendar_scale
        diameter_ratio = calendar_radius / upper_radius
        center_gap = (
            1067 + calendar_translate - (612 + upper_translate)
            - upper_radius - calendar_radius
        )
        core_ratio = 101 * core_scale / 118

        self.assertGreaterEqual(diameter_ratio, 0.9)
        self.assertLessEqual(diameter_ratio, 1.1)
        min_diameter = min(2 * upper_radius, 2 * calendar_radius)
        self.assertGreaterEqual(center_gap, -0.1 * min_diameter)
        self.assertLessEqual(center_gap, 0.08 * min_diameter)
        self.assertGreaterEqual(core_ratio, 0.68)
        self.assertLessEqual(core_ratio, 0.8)

    def test_prague_orloj_calendar_keeps_art_glass_and_figures_separate(self):
        root = Path(__file__).parent
        html = (root / "index.html").read_text(encoding="utf-8")
        calendar_asset = root / "assets/prague-orloj/calendar-dial-v1.svg"

        self.assertTrue(calendar_asset.is_file())
        calendar_svg = calendar_asset.read_text(encoding="utf-8")
        self.assertEqual(calendar_svg.count('href="#monthBase"'), 12)
        self.assertEqual(calendar_svg.count('data-zodiac="'), 12)
        self.assertNotIn("&#9800;", calendar_svg)
        self.assertIn('class="orloj-calendar-art"', html)
        self.assertIn('class="orloj-calendar-glass"', html)
        self.assertIn('class="orloj-calendar-fixed-emblem"', html)
        for figure in (
            "orloj-philosopher",
            "orloj-archangel",
            "orloj-astronomer",
            "orloj-chronicler",
        ):
            self.assertIn(figure, html)

        disk_start = html.index('<g class="orloj-calendar-disk"')
        disk_end = html.index('</g>', html.index('class="orloj-calendar-art"', disk_start))
        rotating_disk = html[disk_start:disk_end]
        self.assertIn('class="orloj-calendar-art"', rotating_disk)
        self.assertNotIn('class="orloj-calendar-glass"', rotating_disk)
        self.assertNotIn('class="orloj-calendar-figures"', rotating_disk)
        self.assertNotIn('class="orloj-calendar-fixed-emblem"', rotating_disk)

    def test_prague_orloj_upper_automata_keep_identity_props_and_layers(self):
        root = Path(__file__).parent
        html = (root / "index.html").read_text(encoding="utf-8")
        css = (root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('class="orloj-upper-figure-housings"', html)
        self.assertIn('class="orloj-upper-figures"', html)
        for slot in (
            "orloj-vanity-slot",
            "orloj-miser-slot",
            "orloj-death-slot",
            "orloj-turk-slot",
        ):
            self.assertIn(slot, html)
        for identity_detail in (
            "orloj-mirror-face",
            "orloj-purse",
            "orloj-cane",
            "orloj-hourglass",
            "orloj-bell-rope",
            "orloj-lute-body",
            "orloj-lute-neck",
        ):
            self.assertIn(identity_detail, html)
        for animated_selector in (
            ".orloj-mirror",
            ".orloj-miser",
            ".orloj-death-arm",
            ".orloj-turk",
        ):
            self.assertIn(animated_selector, css)


class CodexRolloutMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temp_directory.name)
        self.rollout_path = self.codex_home / "sessions" / "rollout-test.jsonl"
        self.rollout_path.parent.mkdir(parents=True)
        self.rollout_path.write_text("", encoding="utf-8")
        self.thread_id = "thread-1"
        self._create_state_database()
        self.monitor = reminder_run.CodexRolloutMonitor(
            codex_home=self.codex_home,
            poll_interval=0.02,
        )
        self.monitor.start()

    def tearDown(self):
        self.monitor.close()
        self.temp_directory.cleanup()

    def _create_state_database(self):
        connection = sqlite3.connect(self.codex_home / "state_5.sqlite")
        connection.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL,
                title TEXT NOT NULL,
                name TEXT,
                preview TEXT NOT NULL DEFAULT '',
                model TEXT,
                reasoning_effort TEXT,
                cwd TEXT,
                updated_at INTEGER NOT NULL,
                updated_at_ms INTEGER,
                recency_at INTEGER NOT NULL DEFAULT 0,
                recency_at_ms INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO threads (
                id, rollout_path, title, name, preview, model, reasoning_effort, cwd, updated_at, updated_at_ms,
                recency_at, recency_at_ms, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                self.thread_id,
                str(self.rollout_path),
                "测试对话",
                None,
                "预览",
                "gpt-5.6-sol",
                "xhigh",
                "/workspace/demo",
                100,
                100_000,
                100,
                100_000,
            ),
        )
        connection.commit()
        connection.close()

    def _append_event(self, event_type, turn_id, **payload):
        event = {
            "timestamp": "2026-08-17T00:00:00Z",
            "type": "event_msg",
            "payload": {"type": event_type, "turn_id": turn_id, **payload},
        }
        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _append_record(self, record_type, payload, timestamp="2026-08-17T00:00:01Z"):
        record = {"timestamp": timestamp, "type": record_type, "payload": payload}
        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _wait_for_status(self, predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.monitor.thread_statuses([self.thread_id])[0]
            if predicate(status):
                return status
            time.sleep(0.01)
        self.fail("Codex 状态没有在时限内更新")

    def test_existing_completion_initializes_snapshot_without_replay(self):
        self._append_event("task_started", "turn-old", started_at=10)
        self._append_event("task_complete", "turn-old", completed_at=20)

        status = self.monitor.thread_statuses([self.thread_id])[0]

        self.assertTrue(status["exists"])
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["latestCompletedTurnId"], "turn-old")
        self.assertEqual(status["latestCompletedAt"], 20)

    def test_appended_completion_is_detected_within_one_second(self):
        self._append_event("task_complete", "turn-old", completed_at=20)
        self.monitor.thread_statuses([self.thread_id])

        self._append_event("task_started", "turn-new", started_at=30)
        active = self._wait_for_status(lambda status: status["status"] == "active")
        self.assertEqual(active["latestCompletedTurnId"], "turn-old")

        started = time.monotonic()
        self._append_event("task_complete", "turn-new", completed_at=40)
        completed = self._wait_for_status(
            lambda status: status["latestCompletedTurnId"] == "turn-new"
        )

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(completed["status"], "idle")
        self.assertEqual(completed["latestCompletedAt"], 40)

    def test_live_phase_model_and_effort_follow_rollout_items(self):
        self.monitor.thread_statuses([self.thread_id])
        self._append_event("task_started", "turn-live", started_at=100)
        reasoning = self._wait_for_status(lambda status: status.get("phase") == "reasoning")
        self.assertEqual(reasoning["model"], "gpt-5.6-sol")
        self.assertEqual(reasoning["reasoningEffort"], "xhigh")
        self.assertEqual(reasoning["cwd"], "/workspace/demo")

        self._append_record(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "status": "completed", "call_id": "call-1"},
            "2026-08-17T00:00:02Z",
        )
        executing = self._wait_for_status(lambda status: status.get("phase") == "executing")
        self.assertEqual(executing["phaseLabel"], "执行工具")
        self.assertEqual(executing["activityStartedAt"], 1786924802)

        self._append_record(
            "response_item",
            {"type": "custom_tool_call_output", "call_id": "call-1", "output": "ok"},
            "2026-08-17T00:00:03Z",
        )
        self._wait_for_status(lambda status: status.get("phase") == "reasoning")

        self._append_record(
            "response_item",
            {"type": "message", "role": "assistant", "phase": "commentary", "content": []},
            "2026-08-17T00:00:04Z",
        )
        outputting = self._wait_for_status(lambda status: status.get("phase") == "outputting")
        self.assertEqual(outputting["phaseLabel"], "AI 输出")

        self._append_event("task_complete", "turn-live", completed_at=110)
        idle = self._wait_for_status(lambda status: status.get("status") == "idle")
        self.assertEqual(idle["phase"], "idle")
        self.assertEqual(idle["phaseLabel"], "保持关注")

    def test_aborted_turn_does_not_replace_latest_completion(self):
        self._append_event("task_complete", "turn-old", completed_at=20)
        self.monitor.thread_statuses([self.thread_id])

        self._append_event("task_started", "turn-aborted", started_at=30)
        self._wait_for_status(lambda status: status["status"] == "active")
        self._append_event("turn_aborted", "turn-aborted", completed_at=35)
        status = self._wait_for_status(lambda status: status["status"] == "idle")

        self.assertEqual(status["latestCompletedTurnId"], "turn-old")

    def test_partial_json_line_waits_until_the_line_is_complete(self):
        self._append_event("task_complete", "turn-old", completed_at=20)
        self.monitor.thread_statuses([self.thread_id])
        event = json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-new",
                    "completed_at": 40,
                },
            }
        )
        midpoint = len(event) // 2
        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(event[:midpoint])
            file.flush()

        time.sleep(0.08)
        unchanged = self.monitor.thread_statuses([self.thread_id])[0]
        self.assertEqual(unchanged["latestCompletedTurnId"], "turn-old")

        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(event[midpoint:] + "\n")
        completed = self._wait_for_status(
            lambda status: status["latestCompletedTurnId"] == "turn-new"
        )
        self.assertEqual(completed["status"], "idle")

    def test_thread_list_uses_local_state_database(self):
        threads = self.monitor.list_threads()

        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["id"], self.thread_id)
        self.assertEqual(threads[0]["name"], "测试对话")
        self.assertEqual(threads[0]["model"], "gpt-5.6-sol")
        self.assertEqual(threads[0]["reasoningEffort"], "xhigh")

    def test_explicit_rollout_source_remains_available_after_thread_is_archived(self):
        connection = sqlite3.connect(self.codex_home / "state_5.sqlite")
        connection.execute(
            "UPDATE threads SET archived = 1 WHERE id = ?", (self.thread_id,)
        )
        connection.commit()
        connection.close()

        self.assertEqual(self.monitor.list_threads(), [])
        sources = self.monitor.rollout_sources([self.thread_id])

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["id"], self.thread_id)
        self.assertEqual(sources[0]["rolloutPath"], self.rollout_path)


class ReminderHandlerThreadNameTests(unittest.TestCase):
    def test_thread_reference_parser_keeps_ssh_host_separate(self):
        parsed = reminder_run.urllib.parse.urlparse(
            "/api/codex/status?id=local-id&id=ssh-192-168-100-255%3A%3Aremote-id&id=unknown%3A%3Aignored"
        )
        handler = object.__new__(reminder_run.ReminderHandler)
        self.assertEqual(handler._thread_refs(parsed), [
            {"hostId": "local", "id": "local-id", "ref": "local-id"},
            {"hostId": "ssh-192-168-100-255", "id": "remote-id", "ref": "ssh-192-168-100-255::remote-id"},
            {"hostId": "local", "id": "unknown::ignored", "ref": "unknown::ignored"},
        ])

    def test_user_assigned_name_wins_for_list_and_status_updates(self):
        thread_id = "thread-1"

        class FakeBridge:
            def list_threads(self):
                return [{"id": thread_id, "name": "运控工程师1.0", "preview": "首次对话"}]

            def cached_thread_summaries(self, thread_ids):
                return {
                    thread_id: {
                        "id": thread_id,
                        "name": "运控工程师1.0",
                        "preview": "首次对话",
                    }
                }

        class FakeMonitor:
            revision = 1
            stopped = True

            def list_threads(self):
                return [{"id": thread_id, "name": "首次对话", "preview": "首次对话"}]

            def thread_statuses(self, thread_ids):
                return [
                    {
                        "id": thread_id,
                        "name": "首次对话",
                        "status": "idle",
                        "exists": True,
                    }
                ]

            def wait_for_change(self, thread_ids, after_revision, timeout):
                return self.revision, self.thread_statuses(thread_ids)

        handler = object.__new__(reminder_run.ReminderHandler)
        with (
            mock.patch.object(reminder_run, "CODEX_BRIDGE", FakeBridge()),
            mock.patch.object(reminder_run, "CODEX_MONITOR", FakeMonitor()),
        ):
            listed = handler._list_codex_threads()
            statuses = handler._codex_statuses([thread_id])

            streamed = []
            handler.send_response = lambda status: None
            handler.send_header = lambda name, value: None
            handler.end_headers = lambda: None
            handler._write_sse = lambda revision, payload: streamed.extend(payload)
            handler._codex_events([thread_id])

        self.assertEqual(listed[0]["name"], "运控工程师1.0")
        self.assertEqual(statuses[0]["name"], "运控工程师1.0")
        self.assertEqual(streamed[0]["name"], "运控工程师1.0")


class CodexRolloutWorkLogReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.rollout_path = Path(self.temp_directory.name) / "rollout-test.jsonl"

    def tearDown(self):
        self.temp_directory.cleanup()

    def _append(self, timestamp, event_type, **payload):
        event = {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {"type": event_type, **payload},
        }
        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _source(self):
        return {
            "id": "thread-1",
            "name": "测试对话",
            "preview": "测试预览",
            "rolloutPath": self.rollout_path,
        }

    def test_reverse_scan_stops_before_large_old_prefix_and_keeps_complete_lines(self):
        old_noise = {
            "timestamp": "1970-01-01T00:00:50Z",
            "type": "event_msg",
            "payload": {"type": "token_count", "value": "x" * 180},
        }
        with self.rollout_path.open("w", encoding="utf-8") as file:
            for _ in range(2500):
                file.write(json.dumps(old_noise) + "\n")

        self._append(
            "1970-01-01T00:01:40Z",
            "task_started",
            turn_id="turn-old",
            started_at=100,
        )
        self._append("1970-01-01T00:01:41Z", "user_message", message="旧问题")
        self._append(
            "1970-01-01T00:02:00Z",
            "task_complete",
            turn_id="turn-old",
            started_at=100,
            completed_at=120,
        )
        self._append(
            "1970-01-01T00:03:20Z",
            "task_started",
            turn_id="turn-new",
            started_at=200,
        )
        self._append("1970-01-01T00:03:21Z", "user_message", message="新问题")
        self._append(
            "1970-01-01T00:03:22Z",
            "agent_message",
            message="过程更新",
            phase="commentary",
        )
        final_answer = "新回复" + "内容" * 2500
        self._append(
            "1970-01-01T00:03:39Z",
            "agent_message",
            message=final_answer,
            phase="final_answer",
        )
        self._append(
            "1970-01-01T00:03:40Z",
            "task_complete",
            turn_id="turn-new",
            started_at=200,
            completed_at=220,
        )
        with self.rollout_path.open("ab") as file:
            file.write(b'{"timestamp":"partial"')

        scan = reminder_run._scan_rollout_window(
            self.rollout_path,
            since=150,
            chunk_size=128,
        )
        log = reminder_run._rollout_work_log(
            self._source(),
            since=150,
            until=None,
            include_process=False,
            chunk_size=128,
        )

        self.assertTrue(scan.reached_boundary)
        self.assertLess(scan.bytes_read, self.rollout_path.stat().st_size // 4)
        self.assertEqual([turn["id"] for turn in log["turns"]], ["turn-new"])
        self.assertEqual(
            [item["text"] for item in log["turns"][0]["items"]],
            ["新问题", final_answer],
        )
        self.assertEqual(log["turns"][0]["status"], "completed")

    def test_rollout_work_log_honors_until_and_process_option(self):
        for index, started_at in enumerate((100, 200), start=1):
            completed_at = started_at + 20
            minute = 1 if index == 1 else 3
            self._append(
                f"1970-01-01T00:0{minute}:40Z",
                "task_started",
                turn_id=f"turn-{index}",
                started_at=started_at,
            )
            self._append(
                f"1970-01-01T00:0{minute}:41Z",
                "user_message",
                message=f"问题{index}",
            )
            self._append(
                f"1970-01-01T00:0{minute}:42Z",
                "agent_message",
                message=f"过程{index}",
                phase="commentary",
            )
            self._append(
                f"1970-01-01T00:0{minute}:50Z",
                "agent_message",
                message=f"回复{index}",
                phase="final_answer",
            )
            self._append(
                f"1970-01-01T00:0{minute}:59Z",
                "task_complete",
                turn_id=f"turn-{index}",
                started_at=started_at,
                completed_at=completed_at,
            )

        without_process = reminder_run._rollout_work_log(
            self._source(),
            since=50,
            until=150,
            include_process=False,
            chunk_size=64,
        )
        with_process = reminder_run._rollout_work_log(
            self._source(),
            since=150,
            until=None,
            include_process=True,
            chunk_size=64,
        )

        self.assertEqual([turn["id"] for turn in without_process["turns"]], ["turn-1"])
        self.assertEqual(
            [item["text"] for item in without_process["turns"][0]["items"]],
            ["问题1", "回复1"],
        )
        self.assertEqual([turn["id"] for turn in with_process["turns"]], ["turn-2"])
        self.assertEqual(
            [item["text"] for item in with_process["turns"][0]["items"]],
            ["问题2", "过程2", "回复2"],
        )

    def test_turn_started_before_shift_is_kept_when_it_completed_after_shift(self):
        self._append(
            "1970-01-01T00:05:00Z",
            "task_started",
            turn_id="turn-crossing",
            started_at=100,
        )
        self._append("1970-01-01T00:01:41Z", "user_message", message="跨班次问题")
        with self.rollout_path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "timestamp": "1970-01-01T00:01:41Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "跨班次问题"}],
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        self._append(
            "1970-01-01T00:03:20Z",
            "agent_message",
            message="跨班次回复",
            phase="final_answer",
        )
        self._append(
            "1970-01-01T00:03:21Z",
            "task_complete",
            turn_id="turn-crossing",
            started_at=100,
            completed_at=201,
        )

        log = reminder_run._rollout_work_log(
            self._source(),
            since=150,
            until=None,
            include_process=False,
            chunk_size=64,
        )

        self.assertEqual([turn["id"] for turn in log["turns"]], ["turn-crossing"])
        self.assertEqual(
            [item["text"] for item in log["turns"][0]["items"]],
            ["跨班次问题", "跨班次回复"],
        )

    def test_thread_rollback_removes_retracted_turns(self):
        for index, started_at in enumerate((100, 200), start=1):
            self._append(
                f"1970-01-01T00:0{index}:00Z",
                "task_started",
                turn_id=f"turn-{index}",
                started_at=started_at,
            )
            self._append(
                f"1970-01-01T00:0{index}:01Z",
                "user_message",
                message=f"问题{index}",
            )
            self._append(
                f"1970-01-01T00:0{index}:02Z",
                "task_complete",
                turn_id=f"turn-{index}",
                started_at=started_at,
                completed_at=started_at + 20,
            )
        self._append(
            "1970-01-01T00:04:00Z",
            "thread_rolled_back",
            num_turns=1,
        )

        log = reminder_run._rollout_work_log(
            self._source(),
            since=50,
            until=None,
            include_process=True,
            chunk_size=64,
        )

        self.assertEqual([turn["id"] for turn in log["turns"]], ["turn-1"])

    def test_reader_caches_stable_rollout_and_invalidates_after_append(self):
        self._append(
            "1970-01-01T00:03:20Z",
            "task_started",
            turn_id="turn-1",
            started_at=200,
        )
        self._append("1970-01-01T00:03:21Z", "user_message", message="问题")

        class FakeMonitor:
            def rollout_sources(_self, thread_ids):
                return [self._source() for _ in thread_ids]

        class FailingBridge:
            def work_logs(self, *args, **kwargs):
                raise AssertionError("不应回退到完整 thread/read")

        reader = reminder_run.CodexWorkLogReader(
            FakeMonitor(),
            FailingBridge(),
            max_workers=1,
            chunk_size=64,
        )
        original_scan = reminder_run._scan_rollout_window
        with mock.patch.object(
            reminder_run,
            "_scan_rollout_window",
            wraps=original_scan,
        ) as scan:
            first = reader.work_logs(["thread-1"], 150, None, True)
            second = reader.work_logs(["thread-1"], 150, None, True)
            self._append(
                "1970-01-01T00:03:40Z",
                "task_complete",
                turn_id="turn-1",
                started_at=200,
                completed_at=220,
            )
            third = reader.work_logs(["thread-1"], 150, None, True)

        self.assertEqual(scan.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["turns"][0]["status"], "inProgress")
        self.assertEqual(third[0]["turns"][0]["status"], "completed")


class CodexWorkLogTests(unittest.TestCase):
    def test_thread_work_log_filters_turns_since_shift_start(self):
        thread = {
            "id": "thread-1",
            "name": "测试对话",
            "turns": [
                {
                    "id": "turn-old",
                    "startedAt": 100,
                    "completedAt": 120,
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "content": [{"type": "input_text", "text": "旧问题"}],
                        }
                    ],
                },
                {
                    "id": "turn-new",
                    "startedAt": 170,
                    "completedAt": 200,
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "content": [{"type": "input_text", "text": "新问题"}],
                        },
                        {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": "新回复",
                        },
                    ],
                },
            ],
        }

        log = reminder_run._thread_work_log(
            thread,
            since=150,
            until=None,
            include_process=True,
        )

        self.assertEqual([turn["id"] for turn in log["turns"]], ["turn-new"])
        self.assertEqual(log["turns"][0]["items"][0]["text"], "新问题")
        self.assertEqual(log["turns"][0]["items"][1]["text"], "新回复")

    def test_thread_work_log_can_exclude_process_messages(self):
        thread = {
            "id": "thread-1",
            "name": "测试对话",
            "turns": [
                {
                    "id": "turn-1",
                    "startedAt": 100,
                    "completedAt": 200,
                    "status": "completed",
                    "items": [
                        {
                            "type": "agentMessage",
                            "phase": "commentary",
                            "text": "过程更新",
                        },
                        {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": "最终回复",
                        },
                    ],
                }
            ],
        }

        log = reminder_run._thread_work_log(
            thread,
            since=None,
            until=None,
            include_process=False,
        )

        self.assertEqual(len(log["turns"]), 1)
        self.assertEqual(log["turns"][0]["items"], [
            {
                "type": "agentMessage",
                "role": "assistant",
                "phase": "final_answer",
                "text": "最终回复",
            }
        ])


class MultiClipboardTests(unittest.TestCase):
    @staticmethod
    def _run_core(script):
        project_root = Path(__file__).parent
        result = subprocess.run(
            ["node", "-e", script, str(project_root / "clipboard-core.js")],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_clipboard_normalization_preserves_text_whitespace_and_formats(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const result = core.normalizeStore({
  version: 1,
  items: [
    { id: "text", title: "原文", content: "  第一行\n\t第二行\n", format: "text", createdAt: 10, updatedAt: 20 },
    { id: "md", title: "Markdown", content: "# 标题", format: "md", viewMode: "source", createdAt: 30, updatedAt: 40 },
    { id: "md", title: "重复", content: "x", format: "unknown", createdAt: 50, updatedAt: 60 },
  ],
});
console.log(JSON.stringify(result));
""")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["items"][0]["content"], "  第一行\n\t第二行\n")
        self.assertEqual(result["items"][0]["format"], "text")
        self.assertEqual(result["items"][1]["format"], "markdown")
        self.assertEqual(result["items"][1]["viewMode"], "source")
        self.assertEqual(len({item["id"] for item in result["items"]}), 3)

    def test_clipboard_search_filter_and_pin_sort_are_stable(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const items = [
  { id: "old", title: "Alpha", content: "普通文本", format: "text", pinned: false, createdAt: 1, updatedAt: 10 },
  { id: "new", title: "Beta", content: "ALPHA in markdown", format: "markdown", pinned: false, createdAt: 2, updatedAt: 30 },
  { id: "pin", title: "Pinned", content: "alpha", format: "text", pinned: true, createdAt: 3, updatedAt: 20 },
];
const all = core.filterAndSortItems(items, "alpha", "all").map((item) => item.id);
const markdown = core.filterAndSortItems(items, "alpha", "markdown").map((item) => item.id);
console.log(JSON.stringify({ all, markdown, original: items.map((item) => item.id) }));
""")
        self.assertEqual(result["all"], ["pin", "new", "old"])
        self.assertEqual(result["markdown"], ["new"])
        self.assertEqual(result["original"], ["old", "new", "pin"])

    def test_clipboard_markdown_parser_keeps_html_inert_and_rejects_unsafe_urls(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const source = [
  "# 标题",
  "",
  "- **加粗**",
  "- [安全](https://example.com)",
  "- [危险](javascript:alert(1))",
  "",
  "> <img src=x onerror=alert(1)>",
  "",
  "```html",
  "</code><script>alert(1)</script>",
  "```",
].join("\n");
console.log(JSON.stringify({
  blocks: core.parseMarkdown(source),
  safe: core.safeUrl("https://example.com/a"),
  javascript: core.safeUrl("javascript:alert(1)"),
  data: core.safeUrl("data:text/html,x"),
}));
""")
        self.assertEqual(result["safe"], "https://example.com/a")
        self.assertIsNone(result["javascript"])
        self.assertIsNone(result["data"])
        serialized = json.dumps(result["blocks"], ensure_ascii=False)
        self.assertIn("<img src=x onerror=alert(1)>", serialized)
        self.assertIn("</code><script>alert(1)</script>", serialized)
        self.assertIn('"type": "link"', serialized)
        self.assertIn("[危险](javascript:alert(1))", serialized)

    def test_clipboard_markdown_parser_recognizes_gfm_tables(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const source = [
  "| 提交 | 内容 | 主要边界 |",
  "| :--- | :---: | ---: |",
  "| 1 | **老仓策略** | 不改生产行为 |",
  "| 2 | `A | B` | [文档](https://example.com) |",
  "| 3 | 转义 \\| 符号 | 安全显示 |",
].join("\n");
console.log(JSON.stringify(core.parseMarkdown(source)));
""")
        self.assertEqual(len(result), 1)
        table = result[0]
        self.assertEqual(table["type"], "table")
        self.assertEqual(table["alignments"], ["left", "center", "right"])
        self.assertEqual(len(table["headers"]), 3)
        self.assertEqual(len(table["rows"]), 3)
        self.assertEqual(table["rows"][0][1][0]["type"], "strong")
        self.assertEqual(table["rows"][1][1][0], {"type": "code", "value": "A | B"})
        self.assertIn("转义 | 符号", "".join(token.get("value", "") for token in table["rows"][2][1]))

    def test_clipboard_table_renderer_and_responsive_styles_are_present(self):
        project_root = Path(__file__).parent
        script = (project_root / "clipboard.js").read_text(encoding="utf-8")
        css = (project_root / "clipboard.css").read_text(encoding="utf-8")
        self.assertIn('block.type === "table"', script)
        self.assertIn('document.createElement("table")', script)
        self.assertIn('className = "clip-table-wrap"', script)
        self.assertRegex(css, r"\.clip-table-wrap\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(css, r"\.clip-markdown table\s*\{[^}]*border-collapse:\s*collapse")

    def test_clipboard_page_has_entry_accessibility_and_responsive_motion_contracts(self):
        project_root = Path(__file__).parent
        index = (project_root / "index.html").read_text(encoding="utf-8")
        html = (project_root / "clipboard.html").read_text(encoding="utf-8")
        css = (project_root / "clipboard.css").read_text(encoding="utf-8")
        script = (project_root / "clipboard.js").read_text(encoding="utf-8")

        self.assertIn('href="clipboard.html">剪贴板</a>', index)
        for element_id in (
            "clipGrid",
            "clipSearch",
            "newClipButton",
            "clipDialog",
            "clipTitle",
            "clipContent",
            "clipboardToast",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="格式筛选"', html)
        self.assertIn('aria-label="已保存的剪贴内容"', html)
        self.assertRegex(css, r"\.clip-grid\s*\{[^}]*display:\s*grid")
        self.assertRegex(css, r"grid-template-columns:\s*repeat\(auto-fill")
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("card.animate(", script)
        self.assertIn("textContent = item.content", script)
        self.assertNotIn("innerHTML", script)


class CardOrderTests(unittest.TestCase):
    def test_active_work_cards_follow_explicit_stable_priority(self):
        project_root = Path(__file__).parent
        script = r"""
const core = require(process.argv[1]);
const cards = [
  { id: "attention", codexThreadId: "thread-a", codexStatus: "idle", codexDue: false, createdAt: 50 },
  { id: "idle", started: false, createdAt: 10 },
  { id: "countdown", started: true, nextAt: 5000, createdAt: 20 },
  { id: "processing", codexThreadId: "thread-b", codexStatus: "active", codexDue: false, createdAt: 40 },
  { id: "due", started: true, nextAt: 900, createdAt: 30 },
  { id: "attention-2", codexThreadId: "thread-c", codexStatus: "idle", codexDue: false, createdAt: 999 },
];
const sorted = core.sortCards(cards, { workActive: true, now: 1000 }).map((card) => card.id);
console.log(JSON.stringify({ sorted, original: cards.map((card) => card.id) }));
"""
        result = subprocess.run(
            ["node", "-e", script, str(project_root / "card-order-core.js")],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["sorted"], [
            "due",
            "countdown",
            "processing",
            "attention",
            "attention-2",
            "idle",
        ])
        self.assertEqual(payload["original"], [
            "attention",
            "idle",
            "countdown",
            "processing",
            "due",
            "attention-2",
        ])

    def test_card_order_core_loads_before_the_home_app(self):
        project_root = Path(__file__).parent
        index = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")
        self.assertLess(
            index.index('<script src="card-order-core.js"></script>'),
            index.index('<script src="app.js"></script>'),
        )
        self.assertIn("const cardOrderCore = window.CardOrderCore;", app)
        self.assertIn("const sorted = cardOrderCore.sortCards(cards, {", app)


class GraphLayoutTests(unittest.TestCase):
    def test_graph_only_creates_active_model_clusters_and_local_edges(self):
        project_root = Path(__file__).parent
        app = (project_root / "app.js").read_text(encoding="utf-8")
        css = (project_root / "styles.css").read_text(encoding="utf-8")
        html = (project_root / "index.html").read_text(encoding="utf-8")
        self.assertIn('const activeCodexCards = sorted.filter(isGraphThreadActive)', app)
        self.assertIn('class="graph-cluster"', app)
        self.assertIn('class="graph-cluster-links"', app)
        self.assertIn('class="graph-unlinked"', app)
        self.assertIn('aria-label="提醒关系图"', html)
        self.assertRegex(css, r"\.model-bubble\s*\{[^}]*border-radius:\s*50%")
        self.assertRegex(css, r"\.graph-cluster\s*\{[^}]*grid-template-columns:\s*154px")
        self.assertIn(".graph-cluster-links", css)
        self.assertIn('data-phase-label="${escapeHtml(phase)}"', app)
        self.assertRegex(css, r"\.thread-bubble-runtime\s*\{[^}]*display:\s*none")
        self.assertRegex(css, r"\.thread-bubble h2\s*\{[^}]*-webkit-line-clamp:\s*2")
        self.assertIn('linked ? "" : `<div class="thread-bubble-meta">', app)
        self.assertRegex(css, r"\.thread-bubble-head\s*\{[^}]*top:\s*7%")
        self.assertRegex(css, r"\.thread-bubble\.is-attention \.thread-bubble-count,[^}]*display:\s*none")

    def test_three_dimensional_graph_is_local_interactive_and_has_fallback(self):
        project_root = Path(__file__).parent
        app = (project_root / "app.js").read_text(encoding="utf-8")
        graph = (project_root / "graph-3d.js").read_text(encoding="utf-8")
        css = (project_root / "styles.css").read_text(encoding="utf-8")
        three = project_root / "assets" / "vendor" / "three.module.js"
        three_core = project_root / "assets" / "vendor" / "three.core.js"
        self.assertTrue(three.is_file())
        self.assertTrue(three_core.is_file())
        self.assertGreater(three.stat().st_size, 500_000)
        self.assertGreater(three_core.stat().st_size, 1_000_000)
        self.assertIn('import * as THREE from "./assets/vendor/three.module.js"', graph)
        self.assertIn('await import("./graph-3d.js")', app)
        self.assertIn('class="graph-3d-canvas"', app)
        self.assertIn('class="graph-fallback"', app)
        self.assertIn("new THREE.WebGLRenderer", graph)
        self.assertIn("new THREE.Raycaster", graph)
        self.assertIn("flowParticles", graph)
        self.assertIn('canvas.addEventListener("pointerdown"', graph)
        self.assertIn('canvas.addEventListener("wheel"', graph)
        self.assertRegex(css, r"\.graph-3d-shell\s*\{[^}]*height:\s*clamp")
        self.assertIn(".card-grid.is-3d-ready .graph-fallback", css)
        self.assertNotIn("https://", graph)

    def test_reasoning_effort_belongs_to_threads_and_edges_not_model_nodes(self):
        project_root = Path(__file__).parent
        app = (project_root / "app.js").read_text(encoding="utf-8")
        graph = (project_root / "graph-3d.js").read_text(encoding="utf-8")
        self.assertIn('label: modelDisplayLabel(card.codexModel),\n        threadCount: 0,', app)
        self.assertIn('function reasoningEffortLabel(effort)', app)
        self.assertIn('data-reasoning-effort=', app)
        self.assertIn('node.kind === "thread" && node.effort ? effortColor(node.effort)', graph)
        self.assertIn('function threadNodeSubtitle(node)', graph)
        self.assertNotIn('isModel ? effortColor(node.effort)', graph)
        self.assertIn('if (!group.userData.comet) group.userData.label = createLabel', graph)
        self.assertIn('const orbitSeed = textSeed(node.id)', graph)

    def test_active_unread_threads_share_model_without_sharing_effort(self):
        root = Path(__file__).parent
        script = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const functions = ['isGraphThreadActive', 'graph3DNodes'];
const context = { isCodexActiveStatus: s => s === 'active',
  graphState: c => c.codexDue ? 'due' : c.codexStatus === 'active' ? 'processing' : 'attention',
  modelDisplayLabel: x => x, graphPhaseLabel: c => c.codexPhase, formatElapsedSince: () => '1秒' };
vm.createContext(context);
for (const name of functions) {
  const start = src.indexOf('function ' + name + '(');
  const end = src.indexOf('\nfunction ', start + 1);
  vm.runInContext(src.slice(start, end), context);
}
const cards = [
  {id:'a',title:'A',codexThreadId:'a',codexStatus:'active',codexPhase:'reasoning',codexModel:'gpt-5.6-sol',codexReasoningEffort:'low',codexDue:true},
  {id:'b',title:'B',codexThreadId:'b',codexStatus:'active',codexPhase:'outputting',codexModel:'gpt-5.6-sol',codexReasoningEffort:'max'},
  {id:'c',title:'C',codexThreadId:'c',codexStatus:'idle',codexPhase:'idle',codexModel:'gpt-6-astra',codexReasoningEffort:'ultra'},
];
console.log(JSON.stringify(context.graph3DNodes(cards, 1000)));
"""
        result = subprocess.run(["node", "-e", script, str(root / "app.js")], check=True, capture_output=True, text=True)
        nodes = json.loads(result.stdout)
        models = [node for node in nodes if node["kind"] == "model"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["threadCount"], 2)
        self.assertNotIn("effort", models[0])
        threads = {node["id"]: node for node in nodes if node["kind"] == "thread"}
        self.assertEqual(threads["a"]["state"], "due")
        self.assertEqual(threads["a"]["modelId"], threads["b"]["modelId"])
        self.assertEqual(threads["a"]["effort"], "low")
        self.assertEqual(threads["b"]["effort"], "max")
        self.assertIsNone(threads["c"]["modelId"])
        self.assertEqual(threads["c"]["effort"], "")

    def test_orbits_are_non_coplanar_deterministic_and_move_around_their_star(self):
        root = Path(__file__).parent
        script = """
import {createOrbitSpec,orbitPoint} from './graph-3d.js';
const specs = Array.from({length:12},(_,i)=>createOrbitSpec('thread-'+i,i,12));
console.log(JSON.stringify({specs, repeat:createOrbitSpec('thread-0',0,12),
  before:specs.map(s=>orbitPoint(s,0).toArray()), after:specs.map(s=>orbitPoint(s,120).toArray()),
  comet:createOrbitSpec('comet',0,5,true)}));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["repeat"], data["specs"][0])
        self.assertGreater(len({round(s["inclination"], 4) for s in data["specs"]}), 8)
        self.assertGreater(len({s["semiMajor"] for s in data["specs"]}), 5)
        for before, after in zip(data["before"], data["after"]):
            self.assertNotEqual(before, after)
        self.assertGreater(data["comet"]["eccentricity"], max(s["eccentricity"] for s in data["specs"]))

    def test_details_can_be_closed_without_reloading(self):
        root = Path(__file__).parent
        app = (root / "app.js").read_text(encoding="utf-8")
        graph = (root / "graph-3d.js").read_text(encoding="utf-8")
        self.assertIn('data-graph-inspector-close aria-label="关闭节点详情"', app)
        self.assertIn('if (!node) {\n    inspector.hidden = true;', app)
        self.assertIn('if (event.key === "Escape")', app)
        self.assertIn('selectNode(pickedNode(event))', graph)
        self.assertIn('clearSelection()', graph)


class WidgetSummaryServiceTests(unittest.TestCase):
    def test_widget_service_enforces_auth_projection_and_route_isolation(self):
        from widget_service import WidgetPublicApp, WidgetSnapshotStore

        project_root = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary:
            private_dir = Path(temporary) / "private"
            token_path = private_dir / "access-token"
            private_dir.mkdir(parents=True)
            token_path.write_text("test-widget-token\n", encoding="utf-8")
            os.chmod(token_path, 0o600)
            store = WidgetSnapshotStore(private_dir, token_path=token_path)
            saved = store.save_snapshot({
                "work": {
                    "active": True,
                    "startedAt": 1_788_000_000_000,
                    "durationMs": 3_661_000,
                    "completionCount": 7,
                    "note": "不得公开的日报备注",
                },
                "reminders": [
                    {
                        "title": "优先任务",
                        "tag": "Codex",
                        "state": "processing",
                        "dueAt": None,
                        "codexThreadId": "private-thread-id",
                    },
                ],
                "clipboard": ["不得公开"],
                "feishu": {"secret": "不得公开"},
            })
            self.assertEqual(saved["work"]["completionCount"], 7)

            app = WidgetPublicApp(
                store,
                "test-widget-token",
                project_root / "scriptable" / "LumenToday.js",
            )

            def request(path, token=None, method="GET"):
                authorization = f"Bearer {token}" if token else ""
                response = app.handle(method, path, authorization)
                return response.status, response.content_type, response.body

            self.assertEqual(request("/api/today")[0], 401)
            self.assertEqual(request("/api/today", "wrong-token")[0], 401)
            status, content_type, body = request("/api/today", "test-widget-token")
            self.assertEqual(status, 200)
            self.assertIn("application/json", content_type)
            payload = json.loads(body)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["work"]["completionCount"], 7)
            serialized = json.dumps(payload, ensure_ascii=False)
            for secret in ("private-thread-id", "不得公开的日报备注", "clipboard", "feishu"):
                self.assertNotIn(secret, serialized)
            for private_path in ("/api/codex/threads", "/api/feishu/status", "/../run.py"):
                self.assertEqual(request(private_path, "test-widget-token")[0], 404)
            self.assertEqual(request("/api/today", "test-widget-token", "POST")[0], 404)
            script_status, script_type, script_body = request("/LumenToday.js")
            self.assertEqual(script_status, 200)
            self.assertIn("javascript", script_type)
            self.assertNotIn(b"test-widget-token", script_body)

    def test_widget_token_generation_is_idempotent_and_private(self):
        from widget_service import ensure_widget_token

        with tempfile.TemporaryDirectory() as temporary:
            token_path = Path(temporary) / "widget" / "access-token"
            first = ensure_widget_token(token_path)
            second = ensure_widget_token(token_path)
            self.assertEqual(first, second)
            self.assertGreaterEqual(len(first), 40)
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_widget_summary_keeps_the_claimed_browser_as_its_source(self):
        from widget_service import WidgetSnapshotStore

        with tempfile.TemporaryDirectory() as temporary:
            store = WidgetSnapshotStore(Path(temporary))
            store.save_snapshot({
                "sourceId": "main-browser",
                "claimSource": True,
                "work": {"active": False, "completionCount": 8},
                "reminders": [
                    {"title": "真实任务一", "state": "processing"},
                    {"title": "真实任务二", "state": "countdown"},
                ],
                "quote": {"text": "把结果做实。", "source": "本地"},
                "weather": {"location": "杭州", "type": "晴", "current": 29, "min": 25, "max": 33, "rain": 10},
            })
            store.save_snapshot({
                "sourceId": "test-browser",
                "work": {"active": False, "completionCount": 1},
                "reminders": [{"title": "Codex test", "state": "paused"}],
            })
            summary = store.summary()
            self.assertEqual(summary["work"]["completionCount"], 8)
            self.assertEqual([item["title"] for item in summary["reminders"]], ["真实任务一", "真实任务二"])
            self.assertEqual(summary["quote"]["text"], "把结果做实。")
            self.assertEqual(summary["weather"]["current"], 29)

            store.save_snapshot({
                "sourceId": "test-browser",
                "claimSource": True,
                "work": {"active": False, "completionCount": 1},
                "reminders": [{"title": "Codex test", "state": "paused"}],
            })
            self.assertEqual(store.summary()["work"]["completionCount"], 1)

    def test_active_work_session_automatically_becomes_widget_source(self):
        from widget_service import WidgetSnapshotStore

        with tempfile.TemporaryDirectory() as temporary:
            store = WidgetSnapshotStore(Path(temporary))
            store.save_snapshot({
                "sourceId": "old-main-browser",
                "claimSource": True,
                "work": {"active": False, "completionCount": 0},
                "reminders": [],
            })
            store.save_snapshot({
                "sourceId": "working-browser",
                "work": {"active": True, "startedAt": 1_788_148_890_586, "completionCount": 4},
                "reminders": [
                    {"title": "真实进行中", "state": "processing"},
                    {"title": "真实倒计时", "state": "countdown"},
                ],
            })
            active = store.summary()
            self.assertTrue(active["work"]["active"])
            self.assertEqual(active["work"]["completionCount"], 4)
            self.assertEqual(len(active["reminders"]), 2)

            store.save_snapshot({
                "sourceId": "background-test-browser",
                "work": {"active": False, "completionCount": 0},
                "reminders": [{"title": "Codex test", "state": "paused"}],
            })
            self.assertTrue(store.summary()["work"]["active"])

    def test_home_page_syncs_only_the_widget_projection(self):
        project_root = Path(__file__).parent
        app = (project_root / "app.js").read_text(encoding="utf-8")
        run = (project_root / "run.py").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/widget/snapshot"', app)
        self.assertIn("cardOrderCore.sortCards(cards", app)
        self.assertIn('parsed.path == "/api/widget/snapshot"', run)
        self.assertIn("create_widget_server", run)

    def test_scriptable_uses_live_dates_and_fastest_reasonable_refresh(self):
        script = (Path(__file__).parent / "scriptable" / "LumenToday.js").read_text(encoding="utf-8")
        self.assertIn("15 * 60 * 1000", script)
        self.assertIn("URLScheme.forRunningScript()", script)
        self.assertIn("addDate(new Date(work.startedAt))", script)
        self.assertIn("applyTimerStyle()", script)
        self.assertIn('args.queryParameters?.configure === "1"', script)


class WorkHistoryTests(unittest.TestCase):
    @staticmethod
    def _run_core(script):
        project_root = Path(__file__).parent
        result = subprocess.run(
            ["node", "-e", script, str(project_root / "work-history-core.js")],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_work_history_keeps_multiple_shifts_and_uses_beijing_start_day(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const first = core.createEntry({
  id: "first",
  session: { startedAt: Date.parse("2026-08-25T15:30:00Z"), countsByCardId: { a: 3, b: 2 } },
  endedAt: Date.parse("2026-08-25T17:00:00Z"),
  completionCount: 5,
  completions: [{ cardId: "a", title: "任务 A", count: 3 }],
  conversations: [
    { threadId: "thread-a", title: "任务 A", threadName: "Codex A", count: 3 },
    { threadId: "thread-a", title: "重复", threadName: "重复", count: 99 },
    { threadId: "", title: "无效", count: 1 },
  ],
  mood: "focused",
  note: "  跨过北京时间午夜的班次  ",
});
const second = core.createEntry({
  id: "second",
  session: { startedAt: Date.parse("2026-08-25T18:00:00Z"), countsByCardId: { c: 1 } },
  endedAt: Date.parse("2026-08-25T19:00:00Z"),
  completionCount: 1,
  mood: "steady",
});
const store = core.normalizeStore({ version: 1, entries: [second, first] });
console.log(JSON.stringify({
  first,
  ids: store.entries.map((entry) => entry.id),
  dayEntries: core.entriesForDay(store.entries, "2026-08-25").map((entry) => entry.id),
  nextDayEntries: core.entriesForDay(store.entries, "2026-08-26").map((entry) => entry.id),
  summary: core.summarize(store.entries),
}));
""")
        self.assertEqual(result["first"]["dayKey"], "2026-08-25")
        self.assertEqual(result["first"]["note"], "跨过北京时间午夜的班次")
        self.assertEqual(result["first"]["conversations"], [{
            "threadId": "thread-a",
            "title": "任务 A",
            "threadName": "Codex A",
            "count": 3,
        }])
        self.assertEqual(result["ids"], ["first", "second"])
        self.assertEqual(result["dayEntries"], ["first"])
        self.assertEqual(result["nextDayEntries"], ["second"])
        self.assertEqual(result["summary"]["shiftCount"], 2)
        self.assertEqual(result["summary"]["completionCount"], 6)

    def test_work_history_normalizes_corrupt_data_and_builds_stable_month_grid(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const normalized = core.normalizeStore({
  version: 1,
  entries: [
    { id: "ok", startedAt: 10, endedAt: 70, mood: "unknown", note: "x" },
    { id: "backwards", startedAt: 80, endedAt: 20 },
    { id: "ok", startedAt: 100, endedAt: 120 },
  ],
});
const empty = core.normalizeStore(null);
const grid = core.monthGrid("2026-08", Date.parse("2026-08-26T04:00:00Z"));
console.log(JSON.stringify({
  entries: normalized.entries,
  empty,
  gridLength: grid.length,
  first: grid[0],
  last: grid[41],
  today: grid.find((day) => day.isToday),
  previous: core.shiftMonth("2026-01", -1),
  next: core.shiftMonth("2026-12", 1),
}));
""")
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["empty"]["entries"], [])
        self.assertFalse(result["empty"]["invalid"])
        self.assertEqual(result["entries"][0]["mood"], "")
        self.assertEqual(result["gridLength"], 42)
        self.assertEqual(result["first"]["dayKey"], "2026-07-27")
        self.assertEqual(result["last"]["dayKey"], "2026-09-06")
        self.assertEqual(result["today"]["dayKey"], "2026-08-26")
        self.assertEqual(result["previous"], "2025-12")
        self.assertEqual(result["next"], "2027-01")

    def test_work_history_backfill_preserves_original_shift_window(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const original = core.createEntry({
  id: "yesterday",
  session: { startedAt: Date.parse("2026-08-27T00:31:00Z"), countsByCardId: { a: 4 } },
  endedAt: Date.parse("2026-08-27T09:42:00Z"),
  completionCount: 4,
  completions: [{ cardId: "a", title: "昨天的任务", count: 4 }],
  mood: "focused",
  note: "原来的下班感受",
});
const updated = core.normalizeEntry({
  ...original,
  conversations: [
    { threadId: "thread-yesterday", title: "昨天的任务", threadName: "Codex · 昨天", count: 0 },
  ],
});
console.log(JSON.stringify({ original, updated }));
""")
        for key in ("id", "dayKey", "startedAt", "endedAt", "durationMs", "completionCount", "mood", "note"):
            self.assertEqual(result["updated"][key], result["original"][key])
        self.assertEqual(result["updated"]["conversations"][0]["threadId"], "thread-yesterday")

    def test_work_history_groups_backfill_options_by_linked_codex_conversation(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const choices = core.groupConversationChoices(
  [
    { id: "card-a", title: "办公工具", codexThreadId: "thread-office", codexThreadName: "小app" },
    { id: "card-b", title: "同一对话的第二张卡", codexThreadId: "thread-office", codexThreadName: "小app" },
    { id: "card-c", title: "机器人运控", codexThreadId: "thread-motion", codexThreadName: "运控工程师" },
    { id: "card-no-thread", title: "普通提醒" },
  ],
  { "card-a": 2, "card-b": 1, "card-c": 0 },
  [{ threadId: "thread-saved", title: "已删除的旧卡片", threadName: "归档对话", count: 4 }],
);
console.log(JSON.stringify(choices));
""")
        self.assertEqual([choice["threadId"] for choice in result], [
            "thread-saved",
            "thread-office",
            "thread-motion",
        ])
        self.assertEqual(result[1], {
            "threadId": "thread-office",
            "title": "办公工具",
            "threadName": "小app",
            "count": 3,
        })
        self.assertEqual(result[2]["count"], 0)

    def test_work_history_keeps_local_and_ssh_threads_separate(self):
        result = self._run_core(r"""
const core = require(process.argv[1]);
const choices = core.groupConversationChoices(
  [
    { id: "local-card", title: "本机对话", codexThreadId: "same-id", codexHost: "local", codexThreadName: "本机" },
    { id: "remote-card", title: "SSH对话", codexThreadId: "same-id", codexHost: "ssh-192-168-100-255", codexThreadName: "远端" },
  ],
  { "local-card": 1, "remote-card": 2 },
);
console.log(JSON.stringify(choices));
""")
        self.assertEqual(len(result), 2)
        self.assertEqual({choice.get("hostId", "local") for choice in result}, {"local", "ssh-192-168-100-255"})
        self.assertEqual({choice["count"] for choice in result}, {1, 2})

    def test_work_history_page_and_reflection_flow_keep_storage_and_motion_contracts(self):
        project_root = Path(__file__).parent
        index = (project_root / "index.html").read_text(encoding="utf-8")
        app = (project_root / "app.js").read_text(encoding="utf-8")
        html = (project_root / "history.html").read_text(encoding="utf-8")
        css = (project_root / "history.css").read_text(encoding="utf-8")
        script = (project_root / "history.js").read_text(encoding="utf-8")

        self.assertIn('href="history.html">历史</a>', index)
        self.assertLess(index.index('<script src="work-history-core.js"></script>'), index.index('<script src="app.js"></script>'))
        for element_id in (
            "workReflectionDialog",
            "workReflectionForm",
            "reflectionDuration",
            "reflectionCount",
            "workReflectionNote",
            "workReflectionThreads",
            "workReflectionThreadCount",
            "toggleReflectionThreads",
            "confirmWorkReflection",
        ):
            self.assertIn(f'id="{element_id}"', index)
        for element_id in (
            "historyCalendarGrid",
            "historyDayDetail",
            "monthDuration",
            "monthCompletions",
            "historyShiftList",
            "historyConversationDialog",
            "historyConversationForm",
            "historyConversationRange",
            "historyConversationSearch",
            "historyConversationPicker",
            "saveHistoryConversations",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('const WORK_HISTORY_KEY = "lumen-reminder-work-history-v1";', app)
        self.assertIn("conversations: selectedWorkConversations()", app)
        self.assertIn("return workHistoryCore.groupConversationChoices(cards, workSession.countsByCardId);", app)
        self.assertIn('id="reportBackLink"', (project_root / "work-log.html").read_text(encoding="utf-8"))
        work_log = (project_root / "work-log.js").read_text(encoding="utf-8")
        self.assertIn("loadHistoricalContext()", work_log)
        self.assertIn('work-log.html?history=${encodeURIComponent(entry.id)}', script)
        self.assertIn("core.groupConversationChoices(reminderCards, entry.countsByCardId, entry.conversations)", script)
        self.assertNotIn('/api/codex/threads', script)
        self.assertIn("core.normalizeEntry({ ...entry, conversations })", script)
        self.assertIn("localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))", script)
        self.assertIn("读取它在这 ${formatDuration(entry.durationMs)} 班次窗口内的全部消息", script)
        persist_index = app.index("if (!persistWorkHistoryEntry(entry))")
        self.assertLess(persist_index, app.index("endWorkSession(endedAt);", persist_index))
        self.assertRegex(css, r"\.history-calendar-grid\s*\{[^}]*gap:")
        self.assertIn("grid-template-columns: repeat(7, minmax(0, 1fr))", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("calendarGrid.animate(", script)
        self.assertIn("textContent = text", script)
        self.assertNotIn("innerHTML", script)

    def test_home_actions_use_compact_two_row_grid(self):
        css = (Path(__file__).parent / "styles.css").read_text(encoding="utf-8")
        actions = re.search(r"\.topbar-actions\s*\{(?P<body>[^}]*)\}", css)
        self.assertIsNotNone(actions)
        body = actions.group("body")
        self.assertIn("display: grid", body)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", body)
        self.assertIn("width: min(330px, 100%)", body)


if __name__ == "__main__":
    unittest.main()
