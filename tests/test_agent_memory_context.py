import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import agent_memory_context


class AgentMemoryContextTests(unittest.TestCase):
    def test_build_context_contains_core_memory(self):
        context = agent_memory_context.build_context(agent_memory_context.SOURCE_FILES)
        self.assertIn("MagicQuant Agent Memory", context)
        self.assertIn("User Operating Preference", context)
        self.assertIn("K_5M Freeze", context)

    def test_scrub_secrets(self):
        text = "TG_BOT_TOKEN=123456789:abcdefghijklmnopqrstuvwxyz"
        self.assertNotIn("123456789:abcdefghijklmnopqrstuvwxyz", agent_memory_context.scrub_secrets(text))


if __name__ == "__main__":
    unittest.main()
