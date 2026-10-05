CREATE DATABASE IF NOT EXISTS malware_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE malware_monitor;

CREATE TABLE servers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  agent_id VARCHAR(64) NOT NULL UNIQUE,
  hostname VARCHAR(255) NOT NULL,
  site_url VARCHAR(512) NULL,
  ip_address VARCHAR(45) NULL,
  agent_version VARCHAR(32) NULL,
  lmd_version VARCHAR(32) NULL,
  last_seen_at DATETIME NULL,
  last_scan_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_servers_last_seen (last_seen_at)
) ENGINE=InnoDB;

CREATE TABLE events (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  server_id BIGINT UNSIGNED NOT NULL,
  scanner VARCHAR(32) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  fingerprint CHAR(64) NULL,
  occurred_at DATETIME NOT NULL,
  received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload JSON NOT NULL,
  INDEX idx_events_server_time (server_id, occurred_at),
  INDEX idx_events_fingerprint (fingerprint),
  CONSTRAINT fk_events_server FOREIGN KEY (server_id) REFERENCES servers(id)
) ENGINE=InnoDB;

CREATE TABLE incidents (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  server_id BIGINT UNSIGNED NOT NULL,
  site_url VARCHAR(512) NULL,
  severity VARCHAR(16) NOT NULL,
  status ENUM('open','acknowledged','resolved') NOT NULL DEFAULT 'open',
  fingerprint CHAR(64) NOT NULL,
  first_seen_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL,
  resolved_at DATETIME NULL,
  alert_sent_at DATETIME NULL,
  INDEX idx_incidents_status (status),
  INDEX idx_incidents_server (server_id),
  UNIQUE KEY uq_active_incident (server_id, fingerprint, status),
  CONSTRAINT fk_incidents_server FOREIGN KEY (server_id) REFERENCES servers(id)
) ENGINE=InnoDB;

CREATE TABLE findings (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  incident_id BIGINT UNSIGNED NOT NULL,
  path TEXT NOT NULL,
  sha256 CHAR(64) NULL,
  signature VARCHAR(255) NULL,
  detection_type VARCHAR(64) NULL,
  first_seen_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL,
  INDEX idx_findings_incident (incident_id),
  INDEX idx_findings_sha256 (sha256),
  CONSTRAINT fk_findings_incident FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE scans (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  server_id BIGINT UNSIGNED NOT NULL,
  scanner VARCHAR(32) NOT NULL,
  scan_type VARCHAR(32) NOT NULL,
  scan_id VARCHAR(64) NULL,
  started_at DATETIME NOT NULL,
  completed_at DATETIME NULL,
  files_scanned BIGINT UNSIGNED DEFAULT 0,
  detections INT UNSIGNED DEFAULT 0,
  status VARCHAR(16) NOT NULL,
  report JSON NULL,
  INDEX idx_scans_server_time (server_id, started_at),
  INDEX idx_scans_status (status),
  CONSTRAINT fk_scans_server FOREIGN KEY (server_id) REFERENCES servers(id)
) ENGINE=InnoDB;
