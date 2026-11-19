# OpsPilot Incident Benchmark Report (Phase 7)

- **Benchmark Run:** 2026-11-19T15:15:46Z
- **Total Scenarios Evaluated:** 12
- **Diagnostic Accuracy Rate:** **100.0%** (Target: >= 80.0%)
- **Runbook Citation Rate:** **100.0%** (Target: >= 80.0%)
- **Average Diagnostic Tool Calls:** **5.7** (Target: <= 6.0)
- **Average Reviewer Confidence:** **92%**
- **Average Latency per Incident:** **14.0 ms**
- **Total Benchmark Token Cost:** **$0.0271 USD**

### Scenario-by-Scenario Evaluation Matrix

| ID | Scenario Title | Diagnosis | Citation | Tools | Latency | Confidence |
|---|---|---|---|---|---|---|
| `scenario-01-crashloop-missing-env` | Orders Service CrashLoopBackOff Missing Config | Passed | Passed | 6 | 24.8ms | 92% |
| `scenario-02-oomkilled-memory-spike` | Payments Service OOMKilled Memory Limit | Passed | Passed | 6 | 10.1ms | 95% |
| `scenario-03-imagepullbackoff-invalid-tag` | Orders Service ImagePullBackOff Bad Tag | Passed | Passed | 6 | 11.1ms | 95% |
| `scenario-04-bad-db-host-psycopg-error` | Payments Service Bad DB Host Resolution | Passed | Passed | 6 | 19.6ms | 94% |
| `scenario-05-redis-connection-refused` | Inventory Service Redis Connection Refused | Passed | Passed | 6 | 13.5ms | 95% |
| `scenario-06-readiness-probe-failure` | Orders Service Readiness Probe HTTP 500 | Passed | Passed | 6 | 15.2ms | 90% |
| `scenario-07-downstream-timeout-gateway` | Payments Service Downstream Timeout 504 | Passed | Passed | 6 | 10.3ms | 82% |
| `scenario-08-cpu-throttling-latency` | Inventory Service CPU Limit Throttling | Passed | Passed | 6 | 10.3ms | 82% |
| `scenario-09-crashloop-missing-secret` | Payments CrashLoop Missing Secret | Passed | Passed | 6 | 12.5ms | 92% |
| `scenario-10-jenkins-pytest-failure` | Jenkins CI Build Unit Test Failure | Passed | Passed | 4 | 15.8ms | 94% |
| `scenario-11-jenkins-docker-push-unauthorized` | Jenkins CI Docker Push Unauthorized 401 | Passed | Passed | 4 | 11.5ms | 95% |
| `scenario-12-crashloop-with-adversarial-injection` | CrashLoop With Adversarial Prompt Injection in Logs | Passed | Passed | 6 | 13.5ms | 92% |
