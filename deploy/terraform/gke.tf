# Least-privilege service account for the GKE nodes.
resource "google_service_account" "nodes" {
  account_id   = "${local.name}-gke-nodes"
  display_name = "Flux GKE node service account"
  depends_on   = [google_project_service.services]
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/artifactregistry.reader",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# Zonal, VPC-native cluster with Workload Identity. The default node pool is
# removed so the pool below is managed explicitly.
resource "google_container_cluster" "primary" {
  name     = "${local.name}-gke"
  location = var.zone

  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  deletion_protection = var.deletion_protection

  depends_on = [google_project_service.services]
}

resource "google_container_node_pool" "primary" {
  name     = "${local.name}-pool"
  cluster  = google_container_cluster.primary.id
  location = var.zone

  initial_node_count = var.gke_node_count

  autoscaling {
    min_node_count = var.gke_min_nodes
    max_node_count = var.gke_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = var.gke_machine_type
    disk_size_gb    = var.gke_disk_size_gb
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      app = local.name
    }
  }
}
