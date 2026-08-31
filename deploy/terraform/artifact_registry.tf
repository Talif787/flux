resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = local.name
  description   = "Flux container images"
  format        = "DOCKER"
  depends_on    = [google_project_service.services]
}
