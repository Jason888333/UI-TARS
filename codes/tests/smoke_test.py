"""
Smoke test: simulates a UI-TARS scenario where the model is asked to open Notepad.

Tests the full pipeline:
  VLM text output -> parse to structured actions -> generate pyautogui code
"""
import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_tars.action_parser import (
    parse_action_to_structure_output,
    parsing_response_to_pyautogui_code,
)

# Screen dimensions for a typical 1920x1080 desktop
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080


class SmokeTestOpenNotepad(unittest.TestCase):
    """Smoke test: open Notepad via taskbar search, type text, verify pipeline."""

    def test_step1_click_start_menu(self):
        """Step 1: Click the Windows Start / search button to begin opening Notepad."""
        vlm_output = (
            "Thought: I need to open Notepad. I'll click on the Windows search/start button in the taskbar.\n"
            "Action: click(start_box='(50, 1060)')"
        )
        actions = parse_action_to_structure_output(
            vlm_output, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
        )
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "click")
        self.assertIn("start_box", action["action_inputs"])
        self.assertIn("Notepad", action["thought"])

        code = parsing_response_to_pyautogui_code(action, SCREEN_HEIGHT, SCREEN_WIDTH)
        self.assertIn("pyautogui.click", code)
        self.assertIn("button='left'", code)
        print(f"  [SMOKE] Step 1 - Click start menu:\n{code}\n")

    def test_step2_type_notepad(self):
        """Step 2: Type 'notepad' in the search bar."""
        vlm_output = (
            "Thought: The search bar is open. I'll type 'notepad' to find the application.\n"
            "Action: type(content='notepad')"
        )
        actions = parse_action_to_structure_output(
            vlm_output, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
        )
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "type")
        self.assertEqual(action["action_inputs"]["content"], "notepad")

        code = parsing_response_to_pyautogui_code(action, SCREEN_HEIGHT, SCREEN_WIDTH)
        self.assertIn("notepad", code)
        print(f"  [SMOKE] Step 2 - Type 'notepad':\n{code}\n")

    def test_step3_click_notepad_result(self):
        """Step 3: Click the Notepad search result to launch it."""
        vlm_output = (
            "Thought: Notepad appeared in the search results. I'll click on it to open it.\n"
            "Action: click(start_box='(300, 400)')"
        )
        actions = parse_action_to_structure_output(
            vlm_output, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
        )
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "click")

        code = parsing_response_to_pyautogui_code(action, SCREEN_HEIGHT, SCREEN_WIDTH)
        self.assertIn("pyautogui.click", code)
        print(f"  [SMOKE] Step 3 - Click Notepad result:\n{code}\n")

    def test_step4_type_hello_world(self):
        """Step 4: Type 'Hello World' into the opened Notepad."""
        vlm_output = (
            "Thought: Notepad is now open. I'll type 'Hello World' in the editor.\n"
            "Action: type(content='Hello World')"
        )
        actions = parse_action_to_structure_output(
            vlm_output, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
        )
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "type")
        self.assertEqual(action["action_inputs"]["content"], "Hello World")

        code = parsing_response_to_pyautogui_code(action, SCREEN_HEIGHT, SCREEN_WIDTH)
        self.assertIn("Hello World", code)
        print(f"  [SMOKE] Step 4 - Type in Notepad:\n{code}\n")

    def test_step5_save_with_hotkey(self):
        """Step 5: Save the file with Ctrl+S."""
        vlm_output = (
            "Thought: I'll save the file using the keyboard shortcut Ctrl+S.\n"
            "Action: hotkey(hotkey='ctrl s')"
        )
        actions = parse_action_to_structure_output(
            vlm_output, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
        )
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "hotkey")

        code = parsing_response_to_pyautogui_code(action, SCREEN_HEIGHT, SCREEN_WIDTH)
        self.assertIn("pyautogui.hotkey", code)
        self.assertIn("ctrl", code)
        self.assertIn("s", code)
        print(f"  [SMOKE] Step 5 - Save with Ctrl+S:\n{code}\n")

    def test_full_notepad_pipeline(self):
        """End-to-end: parse all steps and verify complete pyautogui script."""
        steps = [
            "Thought: Click start menu to search for Notepad.\nAction: click(start_box='(50, 1060)')",
            "Thought: Type notepad in search.\nAction: type(content='notepad')",
            "Thought: Click on the Notepad result.\nAction: click(start_box='(300, 400)')",
            "Thought: Notepad is open, type Hello World.\nAction: type(content='Hello World')",
            "Thought: Save the file.\nAction: hotkey(hotkey='ctrl s')",
        ]

        all_codes = []
        for i, step in enumerate(steps):
            actions = parse_action_to_structure_output(
                step, factor=1000, origin_resized_height=SCREEN_HEIGHT, origin_resized_width=SCREEN_WIDTH
            )
            self.assertGreater(len(actions), 0, f"Step {i+1} produced no actions")
            code = parsing_response_to_pyautogui_code(actions[0], SCREEN_HEIGHT, SCREEN_WIDTH)
            all_codes.append(code)

        full_script = "\n".join(all_codes)
        # Verify the full script contains all expected operations
        self.assertIn("pyautogui.click", full_script)
        self.assertIn("notepad", full_script)
        self.assertIn("Hello World", full_script)
        self.assertIn("pyautogui.hotkey", full_script)
        print(f"\n  [SMOKE] Full Notepad pipeline script:\n{full_script}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
