"""The unified harness — everything that happens around every LLM call.

Production, test, eval, and replay are configurations of one runtime, not
separate systems. The inner graph calls LLMs only through `HarnessExecutor`.
"""
