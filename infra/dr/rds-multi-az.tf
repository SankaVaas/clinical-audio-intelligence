# Terraform: primary datastore (audit log, sessions, tenant/budget data)
# provisioned for automated failover, PITR, and cross-region replication.
# This is the durability layer everything else (audit, cost, tenancy) sits on.

resource "aws_db_instance" "clinical_ai_primary" {
  identifier                  = "clinical-ai-prod"
  engine                      = "postgres"
  engine_version               = "16.3"
  instance_class               = "db.r6g.xlarge"
  multi_az                     = true              # synchronous standby, automatic failover
  storage_encrypted            = true
  kms_key_id                   = var.kms_key_arn
  backup_retention_period      = 35                # days; covers PITR window
  backup_window                 = "03:00-04:00"
  deletion_protection          = true
  copy_tags_to_snapshot        = true
  performance_insights_enabled = true

  # append-only audit_log grows monotonically -- storage autoscaling avoids
  # a full-disk outage becoming an availability incident
  max_allocated_storage        = 1000
}

resource "aws_db_instance" "clinical_ai_replica_dr_region" {
  identifier             = "clinical-ai-dr-replica"
  replicate_source_db    = aws_db_instance.clinical_ai_primary.arn
  instance_class          = "db.r6g.large"
  provider                = aws.dr_region
  storage_encrypted       = true
  kms_key_id              = var.dr_region_kms_key_arn
}
