# What happened during testing

[Português](validation.md)

On 2026-10-22, all 15 checks passed locally in a dedicated kind cluster, with a healthy application and PostgreSQL. The report is [test-20261022T194213Z.json](../evidence/test-20261022T194213Z.json). Cleanup restored two API replicas and one replica each for Mimir and Prometheus A.

Results demonstrate ingestion, logical tenant-data separation, Grafana queries, history after restart with writer stopped, application-failure detection and replay of samples from a short outage window. Retention was read from the active process; deletion of blocks after 24 hours was not tested.

Setup encountered an unsupported validation flag and two relative paths unwritable by the non-root user. Attempts remain in [setup-findings.json](../evidence/setup-findings.json). The API also restarted while the database initialized; setup now waits for the database before applying the API. Mimir path fixes did not broaden permissions.

GitHub Actions execution is recorded separately once complete. A versioned workflow is not itself a passing CI run. Topology, storage and security limitations are documented in the README.
