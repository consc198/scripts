USE malware_monitor;

CREATE TABLE IF NOT EXISTS agent_credentials (
  agent_id VARCHAR(64) PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at DATETIME NULL,
  revoked_at DATETIME NULL,
  INDEX idx_agent_credentials_active (active),
  CONSTRAINT fk_agent_credentials_server
    FOREIGN KEY (agent_id) REFERENCES servers(agent_id) ON DELETE CASCADE
) ENGINE=InnoDB;
