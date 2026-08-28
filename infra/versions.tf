terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # >= 5.0, < 6.0 — pin the major for a predictable first apply
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Partial backend — supply bucket + lock table at init time:
  #   terraform init -backend-config=backend.hcl
  # (see backend.hcl.example). Delete this block to use local state.
  backend "s3" {
    key     = "basketball-analytics/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}
