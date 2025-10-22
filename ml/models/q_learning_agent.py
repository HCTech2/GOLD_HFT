"""Lightweight Q-learning agent for parameter optimisation decisions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import DefaultDict, Hashable, Iterable, List, MutableMapping, Tuple
import json


State = Tuple[Hashable, ...]


@dataclass
class QLearningAgent:
    actions: Tuple[str, ...] = ("trade", "skip", "reduce_volume", "extend_tp")
    alpha: float = 0.1  # learning rate
    gamma: float = 0.95  # discount factor
    epsilon: float = 0.1  # exploration probability
    _q_table: DefaultDict[State, MutableMapping[str, float]] = field(
        default_factory=lambda: defaultdict(lambda: {action: 0.0 for action in QLearningAgent.actions}),
        init=False,
        repr=False,
    )

    def _state_key(self, state: Iterable[Hashable]) -> State:
        return tuple(state)

    def select_action(self, state: Iterable[Hashable]) -> str:
        key = self._state_key(state)
        action_values = self._q_table[key]
        if len(action_values) == 0:
            action_values.update({action: 0.0 for action in self.actions})

        # epsilon-greedy strategy
        import random

        if random.random() < self.epsilon:
            return random.choice(self.actions)
        return max(action_values, key=action_values.get)

    def update(self, state: Iterable[Hashable], action: str, reward: float, next_state: Iterable[Hashable]) -> None:
        if action not in self.actions:
            raise ValueError(f"Action inconnue: {action}")
        key = self._state_key(state)
        next_key = self._state_key(next_state)

        current_value = self._q_table[key][action]
        next_max = max(self._q_table[next_key].values(), default=0.0)
        td_target = reward + self.gamma * next_max
        self._q_table[key][action] = current_value + self.alpha * (td_target - current_value)

    def decay_epsilon(self, factor: float = 0.995, min_epsilon: float = 0.01) -> None:
        self.epsilon = max(min_epsilon, self.epsilon * factor)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialisable = {"actions": self.actions, "alpha": self.alpha, "gamma": self.gamma, "epsilon": self.epsilon, "q_table": {}}
        for state, action_map in self._q_table.items():
            serialisable["q_table"][json.dumps(state)] = action_map
        path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "QLearningAgent":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        agent = cls(actions=tuple(data["actions"]), alpha=data["alpha"], gamma=data["gamma"], epsilon=data["epsilon"])
        for state_str, action_map in data.get("q_table", {}).items():
            state = tuple(json.loads(state_str))
            agent._q_table[state] = dict(action_map)
        return agent
