import os
import argparse
from pathlib import Path

def create_domain_scaffold(domain_name: str, target_dir: str):
    base_path = Path(target_dir)
    os.makedirs(base_path, exist_ok=True)
    
    # 1. Simulator Template
    simulator_template = f'''import numpy as np
from typing import List
from telos.core.contracts.domain_model import DomainSimulator, DomainFacts
from telos.world.world import World

class {domain_name}Simulator(DomainSimulator):
    """
    Plugin: Implements the DSI contract for {domain_name}.
    """
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        raise NotImplementedError("Define allowable actions for {domain_name}")

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        raise NotImplementedError("Define domain physics for {domain_name}")

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        # Project future trajectories using physics
        return []

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        # Report objective domain facts (no mission-specific bias)
        return DomainFacts(state=state, resources={{}}, constraints=[], events=[], metrics={{}})

    def terminal(self, state: np.ndarray) -> bool:
        return False
'''

    # 2. Compliance Test Template
    test_template = f'''import unittest
from tests.test_domain_compliance import DomainComplianceTestSuite
from telos.examples.{domain_name.lower()}.simulator import {domain_name}Simulator

class Test{domain_name}Compliance(DomainComplianceTestSuite):
    __test__ = True
    def setUp(self):
        self.simulator = {domain_name}Simulator()

if __name__ == '__main__':
    unittest.main()
'''

    # Write files
    with open(base_path / "simulator.py", "w") as f:
        f.write(simulator_template)
    
    test_dir = Path("tests") / "compliance"
    os.makedirs(test_dir, exist_ok=True)
    with open(test_dir / f"test_{domain_name.lower()}_compliance.py", "w") as f:
        f.write(test_template)

    print(f"✓ Created {domain_name} scaffold in {target_dir}")
    print(f"✓ Created compliance test in {test_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()
    create_domain_scaffold(args.name, args.dir)
