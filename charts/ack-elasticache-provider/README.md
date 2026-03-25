# ack-elasticache-provider

![Version: 0.0.0-a.placeholder](https://img.shields.io/badge/Version-0.0.0--a.placeholder-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)

Helm chart to manage ACK ElastiCache replication groups

This chart intentionally renders an ACK ElastiCache `ReplicationGroup` even though the chart name is `ack-elasticache-provider`.
The reason is upstream ACK support: `CacheCluster` exposes `transitEncryptionEnabled` in `spec`, but not `atRestEncryptionEnabled`, while `ReplicationGroup` supports both encryption settings.

The sample fixture translates the provided cache cluster values as follows:

- `CacheClusterId` becomes `replicationGroupID`
- `NumCacheNodes: 1` becomes `numNodeGroups: 1` and `replicasPerNodeGroup: 0`
- `PreferredAvailabilityZone` becomes `preferredCacheClusterAZs: ["us-west-2c"]`
- The node type, engine version, subnet group, security groups, maintenance window, snapshot settings, and network settings map directly to the equivalent `ReplicationGroup.spec` fields

This chart follows the same provider pattern as the DocumentDB and OpenSearch charts, but defaults to no Redis AUTH so it matches existing non-auth ElastiCache clusters:

- it creates a connection secret shell
- it exports connection data with `FieldExport`
- it can optionally publish a selected key with `PushSecret`
- by default `auth.mode=disabled`, so `ReplicationGroup.spec.authToken` is omitted and the connection secret gets an empty `PASSWORD`
- if you set `auth.mode=password`, it generates a Redis password and points `ReplicationGroup.spec.authToken` at that generated password key
- if you set `auth.mode=secretRef`, it points ACK at an existing secret reference instead
- if you set `sequencedConnection.enabled=true`, Argo hook jobs create a stable connection secret before sync and patch `ENDPOINT`, `PORT`, and `ARN` into it after ACK reports the primary endpoint

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| annotations | object | `{}` | Extra annotations for the ReplicationGroup object metadata. |
| atRestEncryptionEnabled | string | `nil` | Enable at-rest encryption via `ReplicationGroup.spec.atRestEncryptionEnabled`. |
| auth | object | `{"existingSecret":{"key":"","name":"","namespace":""},"mode":"disabled","password":{"allowRepeat":true,"digits":8,"key":"PASSWORD","length":32,"noUpper":false,"symbols":4},"username":"default"}` | Authentication data written into the generated connection secret and used for `spec.authToken`. |
| auth.existingSecret.key | string | `""` | Existing secret key used when `auth.mode=secretRef`. |
| auth.existingSecret.name | string | `""` | Existing secret name used when `auth.mode=secretRef`. |
| auth.existingSecret.namespace | string | `""` | Optional namespace for the existing secret reference. |
| auth.mode | string | `"disabled"` | Disable AUTH by default, or use a generated Redis password or existing secret reference. |
| auth.password.allowRepeat | bool | `true` | Allow repeated characters. |
| auth.password.digits | int | `8` | Include digits in generated password. |
| auth.password.key | string | `"PASSWORD"` | Key used for the generated password in the connection secret and `spec.authToken`. |
| auth.password.length | int | `32` | Generated password length. |
| auth.password.noUpper | bool | `false` | Disallow upper-case chars. |
| auth.password.symbols | int | `4` | Include symbols in generated password. |
| auth.username | string | `"default"` | Username written to the connection secret. |
| cacheNodeType | string | `nil` | Node type from `ReplicationGroup.spec.cacheNodeType`. |
| cacheSubnetGroupName | string | `nil` | Cache subnet group name from `ReplicationGroup.spec.cacheSubnetGroupName`. |
| connectionSecret | object | `{"annotations":{},"create":true,"name":""}` | Settings for the generated in-cluster connection secret. |
| connectionSecret.annotations | object | `{}` | Additional annotations to place on the connection secret. |
| connectionSecret.create | bool | `true` | Create the connection secret shell object. |
| connectionSecret.name | string | `""` | Name for the generated connection secret. Defaults to `<release>-<chart>-connection`. |
| description | string | `nil` | Description from `ReplicationGroup.spec.description`. |
| engine | string | `nil` | Cache engine from `ReplicationGroup.spec.engine`. |
| engineVersion | string | `nil` | Engine version from `ReplicationGroup.spec.engineVersion`. |
| fieldExport | object | `{"enabled":true,"mappings":[{"key":"ENDPOINT","name":"endpoint","path":".status.nodeGroups.0.primaryEndpoint.address"},{"key":"PORT","name":"port","path":".status.nodeGroups.0.primaryEndpoint.port"},{"key":"ARN","name":"arn","path":".status.ackResourceMetadata.arn"}]}` | FieldExport settings for copying ReplicationGroup status fields into the connection secret. |
| fieldExport.mappings | list | `[{"key":"ENDPOINT","name":"endpoint","path":".status.nodeGroups.0.primaryEndpoint.address"},{"key":"PORT","name":"port","path":".status.nodeGroups.0.primaryEndpoint.port"},{"key":"ARN","name":"arn","path":".status.ackResourceMetadata.arn"}]` | Fields exported from ReplicationGroup status into the generated secret. |
| fullnameOverride | string | `""` |  |
| ipDiscovery | string | `nil` | IP discovery mode from `ReplicationGroup.spec.ipDiscovery`. |
| kmsKeyID | string | `nil` | KMS key ID from `ReplicationGroup.spec.kmsKeyID`. |
| nameOverride | string | `""` |  |
| networkType | string | `nil` | Network type from `ReplicationGroup.spec.networkType`. |
| numNodeGroups | string | `nil` | Number of node groups (shards) from `ReplicationGroup.spec.numNodeGroups`. |
| port | string | `nil` | Port from `ReplicationGroup.spec.port`. |
| preferredCacheClusterAZs | list | `[]` | Availability zones from `ReplicationGroup.spec.preferredCacheClusterAZs`. |
| preferredMaintenanceWindow | string | `nil` | Weekly maintenance window from `ReplicationGroup.spec.preferredMaintenanceWindow`. |
| pushSecret | object | `{"enabled":false,"name":"","refreshInterval":"1h","sourceKey":"ENDPOINT","storeKind":"SecretStore","target":{"name":"","provider":"","type":"Opaque"}}` | External Secrets PushSecret settings for publishing a selected secret key to an external store. |
| pushSecret.target.name | string | `""` | Remote secret name in the target provider. |
| pushSecret.target.provider | string | `""` | External Secrets store ref name (e.g. aws-secrets-manager). |
| pushSecret.target.type | string | `"Opaque"` | Remote provider-specific secret type/property. |
| reflector | object | `{"allowedNamespaces":[],"enabled":false,"pushNamespaces":[]}` | Secret reflector settings for syncing the connection secret across namespaces. |
| reflector.allowedNamespaces | list | `[]` | Namespaces allowed to pull/reflect this secret. |
| reflector.pushNamespaces | list | `[]` | Namespaces to push reflected secrets into. |
| replicasPerNodeGroup | string | `nil` | Replica count per node group from `ReplicationGroup.spec.replicasPerNodeGroup`. |
| replicationGroupID | string | `nil` | ElastiCache replication group identifier from `ReplicationGroup.spec.replicationGroupID`. |
| resourceName | string | `""` | Optional explicit ReplicationGroup metadata.name. Defaults to the chart fullname. |
| securityGroupIDs | list | `[]` | VPC security group IDs from `ReplicationGroup.spec.securityGroupIDs`. |
| sequencedConnection | object | `{"enabled":false,"kubectlImage":"bitnami/kubectl:latest","maxWaitSeconds":3600,"pollIntervalSeconds":15,"syncWave":20,"ttlSecondsAfterFinished":3600}` | Use Argo hook jobs to create a stable connection secret before sync and patch endpoint data after the ReplicationGroup becomes ready. |
| sequencedConnection.enabled | bool | `false` | Enable Argo-hooked secret bootstrapping and connection-data syncing. |
| sequencedConnection.kubectlImage | string | `"bitnami/kubectl:latest"` | kubectl image used by the sequencing jobs. |
| sequencedConnection.maxWaitSeconds | int | `3600` | Maximum time to wait for the ReplicationGroup endpoint to appear. |
| sequencedConnection.pollIntervalSeconds | int | `15` | Poll interval for waiting on the ReplicationGroup primary endpoint. |
| sequencedConnection.syncWave | int | `20` | Sync wave used by the post-resource connection sync job. |
| sequencedConnection.ttlSecondsAfterFinished | int | `3600` | TTL for completed sequencing jobs. |
| snapshotRetentionLimit | string | `nil` | Automatic snapshot retention in days from `ReplicationGroup.spec.snapshotRetentionLimit`. |
| snapshotWindow | string | `nil` | Daily snapshot window from `ReplicationGroup.spec.snapshotWindow`. |
| transitEncryptionEnabled | string | `nil` | Enable in-transit encryption via `ReplicationGroup.spec.transitEncryptionEnabled`. |
