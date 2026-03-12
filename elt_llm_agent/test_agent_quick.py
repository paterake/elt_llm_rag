#!/usr/bin/env python3
"""Quick test: Query the agent about a specific entity."""

from elt_llm_agent import ReActAgent, AgentConfig

# Create agent
agent = ReActAgent(
    AgentConfig(
        model="qwen3.5:9b",
        max_iterations=8,
        verbose=True,  # Show reasoning trace
    )
)

# Test queries from the PARTY domain
queries = [
    "What does the FA Handbook say about Club Official?",
    "What are the governance rules for Match Officials?",
    "What is a Club according to the FA Handbook?",
]

for query in queries:
    print("\n" + "="*80)
    print(f"QUERY: {query}")
    print("="*80)
    
    response = agent.query(query, include_trace=True)
    
    print("\n" + "-"*80)
    print("RESPONSE:")
    print("-"*80)
    print(response.response)
    
    print("\n" + "-"*80)
    print("TOOL CALLS:")
    print("-"*80)
    for tc in response.tool_calls:
        print(f"  Step {tc['step']}: {tc['tool']}")
    
    # Reset conversation between queries
    agent.reset()
