# Routing Design Constraint

The router selects agents from the available agent descriptions.  Preserve that
design boundary.

For a routing-related defect or ambiguity:

- Update the description of the responsible non-router agent or agents.
- When necessary, update the prompt of the responsible non-router agent.
- Do not add intent-specific routing rules to `agents/router/router.prompt` or
  `prompts/templates/router_prompt.txt`.
- Do not add code-level routing overrides, keyword classifiers, or special-case
  branches to solve a routing complaint.

The router prompt must remain generic and make decisions from the supplied
agent descriptions, user request, and available context.
