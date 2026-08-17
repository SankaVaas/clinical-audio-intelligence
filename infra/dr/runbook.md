# Disaster Recovery Runbook

## Objectives
- **RPO (Recovery Point Objective): 5 minutes** — bounded by RDS Multi-AZ
  synchronous replication + continuous WAL shipping for PITR.
- **RTO (Recovery Time Objective): 30 minutes** — bounded by automated RDS
  failover (~1–2 min) plus cluster/app redeploy time from the last Velero
  snapshot in the DR region.

## Failure scenarios and response

### 1. Single pod/node failure
No action required — HPA, PodDisruptionBudget, and topology spread
(`infra/k8s/base/backend-deployment.yaml`) handle this automatically.

### 2. AZ failure
- Compute: `topologySpreadConstraints` already distributes replicas across
  AZs; surviving AZs absorb load, HPA scales to compensate.
- Database: RDS Multi-AZ fails over to the synchronous standby automatically
  (~1–2 min). No manual intervention; monitor `AuditWriteFailure` alert
  during the failover window in case any in-flight writes were dropped.

### 3. Region failure
1. Declare DR — this decision requires on-call incident commander sign-off,
   not automated triggering, given the compliance implications of a
   region-level failover for a clinical system.
2. Promote `clinical_ai_replica_dr_region` to a standalone primary
   (`aws rds promote-read-replica`).
3. Redeploy the application stack into the DR-region cluster from the most
   recent Velero backup (`velero restore create --from-schedule
   clinical-ai-daily`).
4. Repoint DNS (Ingress hostname) to the DR-region load balancer.
5. Run `AuditService.verify_chain()` for every tenant against the promoted
   replica before resuming write traffic — confirm no chain break occurred
   during replication lag at the moment of failure.
6. Post-incident: root-cause review, and a decision on whether to fail back
   or make the DR region the new primary.

## Backup verification
Restore drills are run quarterly against a scratch namespace — an untested
backup is not a backup. Track drill results and time-to-restore per drill in
the audit log (`resource_type = "dr_drill"`) to catch RTO drift over time.

## What's explicitly out of scope here
Multi-region **active-active** serving is not implemented — this is
active-passive DR (single active region, warm standby). Active-active would
require solving cross-region write conflict resolution for the audit log's
hash chain, which is a significant additional design effort beyond
production-readiness baseline.
