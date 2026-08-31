variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  description = "GCP region for regional resources (Artifact Registry, Cloud SQL, subnet)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for the (zonal) GKE cluster. Keep in var.region."
  type        = string
  default     = "us-central1-a"
}

variable "name_prefix" {
  description = "Prefix applied to resource names."
  type        = string
  default     = "flux"
}

# --- Networking ---
variable "subnet_cidr" {
  description = "Primary CIDR for the GKE nodes subnet."
  type        = string
  default     = "10.10.0.0/24"
}

variable "pods_cidr" {
  description = "Secondary CIDR for GKE pods (VPC-native)."
  type        = string
  default     = "10.20.0.0/16"
}

variable "services_cidr" {
  description = "Secondary CIDR for GKE services (VPC-native)."
  type        = string
  default     = "10.30.0.0/20"
}

# --- GKE ---
variable "gke_machine_type" {
  description = "Node machine type."
  type        = string
  default     = "e2-standard-2"
}

variable "gke_node_count" {
  description = "Initial nodes in the pool."
  type        = number
  default     = 1
}

variable "gke_min_nodes" {
  description = "Minimum nodes (node pool autoscaling)."
  type        = number
  default     = 1
}

variable "gke_max_nodes" {
  description = "Maximum nodes (node pool autoscaling)."
  type        = number
  default     = 3
}

variable "gke_disk_size_gb" {
  description = "Node boot disk size."
  type        = number
  default     = 50
}

# --- Cloud SQL ---
variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is cheapest; use a larger tier in production."
  type        = string
  default     = "db-f1-micro"
}

variable "db_version" {
  description = "Cloud SQL PostgreSQL version."
  type        = string
  default     = "POSTGRES_16"
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "flux"
}

variable "db_user" {
  description = "Application database user."
  type        = string
  default     = "flux"
}

# --- Safety ---
variable "deletion_protection" {
  description = "Protect the GKE cluster and Cloud SQL instance from deletion. Set true for production; false makes teardown possible for a demo."
  type        = bool
  default     = false
}
