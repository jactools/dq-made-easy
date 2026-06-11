# Pi Agent Harness Onboarding Guide

> **Feature:** DOC-1.10 Pi Agent Harness onboarding guide
> **Where to find it:** dq-ui assistant surfaces in Suggestions, Connector Workbench, and Data Asset Studio
> **Audience:** analysts, data stewards, and developers using the dq-llm agent harness

## What this guide covers

This guide helps you get started with the Pi Agent Harness integration in DQ-RuleBuilder. It explains where to find the AI assistant in the UI, what to expect from the agent, and how to frame good prompts for the most common workflows.

## Before you start

Make sure the following are available in your environment:

- The dq-llm service is running and reachable from the UI.
- You are signed in with the same SSO / Keycloak identity used by the rest of the platform.
- You have access to the workspace or feature area you want to inspect.

If the assistant panel does not load, check the backend health endpoint and verify that your session is authenticated before retrying.

## Where to use the agent

The existing agent harness is available from the main assistant entry points in the UI:

1. Suggestions — draft or refine natural-language rules and governance recommendations.
2. Connector Workbench — get setup guidance for connector onboarding and validation flows.
3. Data Asset Studio — inspect metadata, lineage, and governance context for data assets.

Use the same agent surface in each page; the only difference is the default prompt and the workflow context that surrounds it.

## Quick start

1. Open the page where you want AI assistance.
2. Find the assistant panel labeled with the relevant workflow (for example, Rule drafting assistant or Metadata browser assistant).
3. Review the default prompt and adjust it to your exact question.
4. Select the agent type that matches your goal.
5. Run the agent and review the response, tool calls, and session details.

## Recommended prompt patterns

### Connector onboarding

Use prompts such as:

- Help me configure this connector for my current workspace.
- What validation steps should I run before I sync this connector?
- Suggest safe secret-handling and discovery checks for this provider.

### Rule drafting

Use prompts such as:

- Turn this natural-language rule into a precise, testable quality rule.
- Suggest candidate attributes and a validation plan for this condition.
- Help me refine this rule description before I save a draft suggestion.

### Metadata and governance review

Use prompts such as:

- Explain the metadata, lineage, and governance context for this asset.
- Which protection checks should I review before I save this asset?
- Highlight the most important gaps in this object version or contract context.

## What the agent returns

The assistant response is designed for review rather than blind automation. You should expect:

- A concise natural-language explanation or recommendation.
- Tool execution details when the agent needs to inspect metadata or related services.
- Session context so you can trace the interaction later if needed.

## Good habits

- Keep prompts specific to the workflow you are in.
- Ask for one focused outcome at a time, such as validation guidance or metadata review.
- Treat the response as a starting point; confirm any risky or operational recommendation in the normal workflow.
- Use the prompt to explain the target context, workspace, or connector you care about.

## Security and operational notes

- Secrets are redacted in logs and responses.
- Agent actions are audited and traced for observability.
- The agent should fail fast on unavailable dependencies rather than returning guessed or stale results.
- Review any recommendation that touches production configuration, access control, or data handling before acting on it.

## Troubleshooting

If the agent does not respond as expected:

- Verify that the dq-llm endpoint is available and that your session is authenticated.
- Re-check the prompt for missing workspace or connector context.
- Try the same task in the most specific workflow surface available for your scenario.
- Review the agent response for explicit error text instead of assuming a silent fallback occurred.

## Summary

The Pi Agent Harness is best used as an assistive workflow layer for connector setup, rule drafting, and metadata exploration. It is most effective when prompts are specific, the workflow context is clear, and the response is reviewed before you act on it.
