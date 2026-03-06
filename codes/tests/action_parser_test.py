import unittest

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re

from ui_tars.action_parser import (
    parsing_response_to_pyautogui_code,
    parse_action,
    parse_action_to_structure_output,
    _to_screen_coords,
    convert_point_to_coordinates,
)


class TestActionParser(unittest.TestCase):
    def test_parse_action(self):
        action_str = "click(point='<point>200 300</point>')"
        result = parse_action(action_str)
        self.assertEqual(result['function'], 'click')
        self.assertEqual(result['args']['point'], '<point>200 300</point>')

    def test_parse_action_to_structure_output(self):
        text = "Thought: test\nAction: click(point='<point>200 300</point>')"
        actions = parse_action_to_structure_output(
            text, factor=1000, origin_resized_height=224, origin_resized_width=224
        )
        self.assertEqual(actions[0]['action_type'], 'click')
        self.assertIn('start_box', actions[0]['action_inputs'])

    def test_parsing_response_to_pyautogui_code(self):
        responses = {"action_type": "hotkey", "action_inputs": {"hotkey": "ctrl v"}}
        code = parsing_response_to_pyautogui_code(responses, 224, 224)
        self.assertIn('pyautogui.hotkey', code)


class TestMouseAccuracy(unittest.TestCase):
    """Tests for mouse coordinate accuracy improvements."""

    def test_to_screen_coords_returns_integers(self):
        """Coordinates must be exact integers, not floats."""
        x, y = _to_screen_coords(0.5, 0.5, 1920, 1080)
        self.assertIsInstance(x, int)
        self.assertIsInstance(y, int)

    def test_to_screen_coords_center(self):
        """Center of screen should be exactly half the dimensions."""
        x, y = _to_screen_coords(0.5, 0.5, 1920, 1080)
        self.assertEqual(x, 960)
        self.assertEqual(y, 540)

    def test_to_screen_coords_origin(self):
        """Origin should be (0, 0)."""
        x, y = _to_screen_coords(0.0, 0.0, 1920, 1080)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

    def test_to_screen_coords_bottom_right(self):
        """Bottom-right corner at (1.0, 1.0) should clamp to max valid pixel."""
        x, y = _to_screen_coords(1.0, 1.0, 1920, 1080)
        self.assertEqual(x, 1919)
        self.assertEqual(y, 1079)

    def test_to_screen_coords_uses_round_not_truncate(self):
        """round() should be used, not int() truncation.

        For 0.999 * 1920 = 1918.08 -> round = 1918, int = 1918 (same)
        For 0.3337 * 1920 = 640.704 -> round = 641, int = 640 (different!)
        """
        x, _ = _to_screen_coords(0.3337, 0.0, 1920, 1080)
        self.assertEqual(x, 641)  # round(640.704) = 641, not int(640.704) = 640

    def test_to_screen_coords_clamping_negative(self):
        """Slightly negative coordinates should clamp to 0."""
        x, y = _to_screen_coords(-0.001, -0.001, 1920, 1080)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)

    def test_to_screen_coords_clamping_overflow(self):
        """Coordinates > 1.0 should clamp to screen bounds."""
        x, y = _to_screen_coords(1.05, 1.05, 1920, 1080)
        self.assertEqual(x, 1919)
        self.assertEqual(y, 1079)

    def test_to_screen_coords_dpi_scale_factor(self):
        """DPI scale factor 2.0: screenshot is 3840x2160 but logical screen is 1920x1080."""
        x, y = _to_screen_coords(0.5, 0.5, 3840, 2160, scale_factor=2.0)
        self.assertEqual(x, 960)
        self.assertEqual(y, 540)

    def test_to_screen_coords_dpi_scale_bounds(self):
        """With scale factor, bounds should be based on logical screen size."""
        x, y = _to_screen_coords(1.0, 1.0, 3840, 2160, scale_factor=2.0)
        self.assertEqual(x, 1919)
        self.assertEqual(y, 1079)

    def test_click_generates_integer_coordinates(self):
        """Generated pyautogui click code should use integer coordinates."""
        response = {
            "action_type": "click",
            "action_inputs": {
                "start_box": "[0.3337, 0.5, 0.3337, 0.5]"
            }
        }
        code = parsing_response_to_pyautogui_code(response, 1080, 1920)
        # Extract coordinates from pyautogui.click(x, y, ...)
        match = re.search(r'pyautogui\.click\((\d+),\s*(\d+)', code)
        self.assertIsNotNone(match, f"Expected integer coords in: {code}")
        x, y = int(match.group(1)), int(match.group(2))
        self.assertEqual(x, 641)  # round(0.3337 * 1920)
        self.assertEqual(y, 540)  # round(0.5 * 1080)

    def test_click_with_scale_factor(self):
        """Click with DPI scale factor should produce logical screen coordinates."""
        response = {
            "action_type": "click",
            "action_inputs": {
                "start_box": "[0.5, 0.5, 0.5, 0.5]"
            }
        }
        code = parsing_response_to_pyautogui_code(
            response, 2160, 3840, scale_factor=2.0)
        match = re.search(r'pyautogui\.click\((\d+),\s*(\d+)', code)
        self.assertIsNotNone(match)
        x, y = int(match.group(1)), int(match.group(2))
        self.assertEqual(x, 960)   # 3840/2 * 0.5 = 960
        self.assertEqual(y, 540)   # 2160/2 * 0.5 = 540

    def test_convert_point_to_coordinates(self):
        """Point conversion should preserve exact coordinates."""
        text = "click(point='<point>200 300</point>')"
        result = convert_point_to_coordinates(text)
        self.assertIn("(200,300)", result)

    def test_full_pipeline_doubao_model(self):
        """End-to-end test: model output -> structured -> pyautogui with doubao model."""
        text = "Thought: Click the button\nAction: click(start_box='(500,500,500,500)')"
        parsed = parse_action_to_structure_output(
            text, factor=1000,
            origin_resized_height=1080, origin_resized_width=1920,
            model_type="doubao"
        )
        code = parsing_response_to_pyautogui_code(parsed, 1080, 1920)
        match = re.search(r'pyautogui\.click\((\d+),\s*(\d+)', code)
        self.assertIsNotNone(match, f"Expected integer coords in: {code}")
        x, y = int(match.group(1)), int(match.group(2))
        # 500/1000 = 0.5 -> 0.5 * 1920 = 960, 0.5 * 1080 = 540
        self.assertEqual(x, 960)
        self.assertEqual(y, 540)


if __name__ == '__main__':
    unittest.main()
