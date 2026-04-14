# Local LLM Routing Architecture

ASCII sketch based on the provided diagram:

```text
+-----------+                           +----------+
| tailscale |                           | telegram |
+-----------+                           +----------+
      |\                                      \
      | \                                      \
      |  \                                      v
      |   \                           +------------------+
      |    +------------------------> | Claw or Hermes   |
      |                               +------------------+
      |                                        |
      v                                        v
+--------------------+              +---------------------------+
| open-webui         |              | LLM router (claw router) |
| "chat UX"          |              +---------------------------+
+--------------------+                        |   \    \     \
                                              |    \    \     \
                                              v     v    v     v
                                   +----------------+  GLM  ChatGPT  MiniMax
                                   | localhost      |
                                   | OpenAI wrapper |
                                   +----------------+
                                              |
                                              v
                                   +----------------+
                                   | local model    |
                                   +----------------+
```
