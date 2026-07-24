# TELOS Operational Guidelines

To maintain the architectural invariance (AIS = 1.0) of the TELOS Runtime, all domain integrations must strictly adhere to these guidelines.

## 1. The Architectural "Hard Wall"
*   **Runtime Core:** The `telos/core/` directory is **IMMUTABLE**. No domain-specific logic (e.g., chess rules, market tickers) may be imported or referenced here.
*   **World Substrate:** All reasoning is performed on the `telos.world.world.World` object. No raw domain data should persist within the Runtime core.

## 2. Plugin Compliance Protocol
To introduce a new domain, you must:

1.  **Use the Scaffolder:** Always start with `python3 telos/tools/scaffolder.py --name [Domain] --dir telos/examples/[domain]`.
2.  **Implement the Contract:** Satisfy the `DomainSimulator` interface in `telos/core/contracts/domain_model.py`.
3.  **Pass Compliance:** The plugin MUST pass the `tests/core/test_domain_compliance.py` test suite before it is registered.
4.  **Audit Registration:** Run `python3 audit/generate_audit.py` to update the `domain_ledger.json` with the new plugin fingerprint.

## 3. The Golden Rule of Portability
If you find yourself needing to modify `telos/core/` to accommodate a domain plugin, **you have created an architectural leak.** 
*   **Action:** Re-evaluate the `DomainSimulator` contract. If a method is missing, propose a contract expansion to the `DSI` rather than hacking the core runtime.

## 4. Stability Validation
New domains must demonstrate stability through the **Invariance Stress Test** (hot-swapping) to prove that the Runtime can reason over the new domain without structural regression.
