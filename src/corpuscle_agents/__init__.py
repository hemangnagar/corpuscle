"""corpuscle_agents: the agent layer. The only package that calls a model.

Agents propose, the core disposes. Everything here reaches the bundle through
corpuscle.tools, which logs every call, and the only thing an agent can produce is a
proposal that a named approver accepts or rejects. Nothing in src/corpuscle imports this.
"""
