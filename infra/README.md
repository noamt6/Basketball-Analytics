# infra/ — Terraform for the AWS deployment

Provisions, in `eu-central-1`:

| File | Resources |
|---|---|
| `versions.tf` | Terraform ≥ 1.6, AWS provider ≥ 5.0, partial S3 backend, provider + `default_tags` |
| `main.tf` | caller-identity / region data, shared `locals` |
| `network.tf` | default-VPC + subnet data, RDS / batch-task / (optional) bastion security groups, optional SSM jump host |
| `rds.tf` | Postgres 16 `db.t4g.micro`, gp3 20 GB (autoscale 100), encrypted, `rds.force_ssl=1`, 7-day backups, private |
| `secrets.tf` | `random_password` + Secrets Manager secret `{host,port,dbname,username,password}` |
| `ecr.tf` | batch-image repo + keep-last-10 lifecycle policy |
| `site.tf` | private S3 bucket + CloudFront (OAC, default `*.cloudfront.net` cert) |
| `ecs.tf` | Fargate cluster + `bball-batch` task definition (no service — run on demand) |
| `iam.tf` | ECS exec/task roles, optional bastion role, `deployer` policy, optional GitHub-OIDC role / IAM user |
| `outputs.tf` | RDS endpoint, secret ARN, ECR URL, bucket, CloudFront id/domain/url, ready `run-task` + `ssm start-session` commands |

**Networking:** default VPC, **no NAT gateway**. The DB is never
`publicly_accessible`. DB-touching jobs run as Fargate tasks in the VPC
(`aws ecs run-task`); for ad-hoc `psql` set `create_bastion = true` and use the
`ssm_port_forward_example` output.

**No custom domain yet** — the dashboard is served from the CloudFront default
domain. Adding one later = an ACM cert in `us-east-1` + a Route 53 alias +
`aliases`/`viewer_certificate` on the distribution.

## One-time prerequisites (create by hand)

1. An S3 bucket for Terraform state + a DynamoDB table for state locking.
2. `aws configure --profile bball` — creds that can create the above.
3. `terraform` ≥ 1.6, `aws` CLI v2 (+ the Session Manager plugin if `create_bastion`).

## Deploy

```bash
cd infra
cp backend.hcl.example backend.hcl        && $EDITOR backend.hcl
cp terraform.tfvars.example terraform.tfvars && $EDITOR terraform.tfvars

export AWS_PROFILE=bball
terraform init -backend-config=backend.hcl
terraform validate
terraform plan
terraform apply
```

Then follow `../DEPLOY.md` (push the image, `run-task migrate` / `ingest` /
`export`, sync the site, invalidate). `terraform output` prints every value and
two copy-paste command strings.

## Notes

* `db_engine_version = "16"` → RDS picks the newest supported 16.x minor.
* `deletion_protection` defaults on. To `terraform destroy`: set
  `db_deletion_protection = false`, apply, then destroy.
* Cost (rough, eu-central-1): RDS `db.t4g.micro` ~$13–15/mo (free-tier eligible
  12 months), S3 + CloudFront cents, Secrets Manager $0.40/mo, Fargate only while
  a task runs, bastion ~$3/mo only if enabled. No NAT.
