output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.primary.name
}

output "cluster_location" {
  description = "GKE cluster location (zone)."
  value       = google_container_cluster.primary.location
}

output "get_credentials_command" {
  description = "Command to configure kubectl for the cluster."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --zone ${google_container_cluster.primary.location} --project ${var.project_id}"
}

output "artifact_registry_repo" {
  description = "Docker repository path for pushing/pulling images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "db_instance_connection_name" {
  description = "Cloud SQL instance connection name."
  value       = google_sql_database_instance.postgres.connection_name
}

output "db_private_ip" {
  description = "Private IP of the Cloud SQL instance (reachable from pods in the VPC)."
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "db_password" {
  description = "Generated database password for the application user."
  value       = random_password.db.result
  sensitive   = true
}

output "database_url" {
  description = "FLUX_DATABASE_URL for the Helm chart (contains the password)."
  value       = "postgresql+asyncpg://${var.db_user}:${random_password.db.result}@${google_sql_database_instance.postgres.private_ip_address}:5432/${var.db_name}"
  sensitive   = true
}
