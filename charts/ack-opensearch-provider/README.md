# ack-opensearch-provider

![Version: 0.0.0-a.placeholder](https://img.shields.io/badge/Version-0.0.0--a.placeholder-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)

Helm chart to manage ACK OpenSearch domains and exported connection secrets

This chart follows the same provider pattern as the DocumentDB and ElastiCache charts:

- it creates a connection secret shell
- it exports connection data with `FieldExport`
- it can optionally publish a selected key with `PushSecret`
- by default `auth.mode=password`, so it generates the OpenSearch admin password into the connection secret
- if you set `auth.mode=irsa`, it writes an empty `PASSWORD` and optionally includes `AWS_ROLE_ARN`
- if you set `sequencedConnection.enabled=true`, Argo hook jobs create a stable connection secret before sync and patch `ENDPOINT` and `ARN` into it after ACK reports the domain endpoint

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| accessPolicies | string | `nil` |  |
| advancedOptions | object | `{}` | Advanced key-value configuration options for the OpenSearch domain. |
| advancedSecurityOptions | object | `{}` | Fine-grained access control settings for the OpenSearch domain. |
| aimlOptions | object | `{}` | AIML feature settings for the OpenSearch domain. |
| annotations | object | `{}` | Extra annotations for the Domain object metadata. |
| auth | object | `{"irsaRoleArn":"","mode":"password","password":{"allowRepeat":true,"digits":8,"key":"PASSWORD","length":32,"noUpper":false,"symbols":4},"username":"admin"}` | Authentication data written into the generated connection secret. |
| auth.irsaRoleArn | string | `""` | Optional IAM role ARN written in IRSA mode. |
| auth.mode | string | `"password"` | Use generated password auth or IRSA (empty password) auth. |
| auth.password.allowRepeat | bool | `true` | Allow repeated characters. |
| auth.password.digits | int | `8` | Include digits in generated password. |
| auth.password.key | string | `"PASSWORD"` | Key used for the generated password in the connection secret. |
| auth.password.length | int | `32` | Generated password length. |
| auth.password.noUpper | bool | `false` | Disallow upper-case chars. |
| auth.password.symbols | int | `4` | Include symbols in generated password. |
| auth.username | string | `"admin"` | Username written to the connection secret. |
| autoTuneOptions | object | `{}` | Auto-Tune maintenance scheduling and rollback settings for the OpenSearch domain. |
| clusterConfig | object | `{}` | Cluster topology and instance sizing settings for the OpenSearch domain. |
| cognitoOptions | object | `{}` | Amazon Cognito authentication settings for the OpenSearch domain. |
| connectionSecret | object | `{"annotations":{},"create":true,"name":""}` | Settings for the generated in-cluster connection secret. |
| connectionSecret.annotations | object | `{}` | Additional annotations to place on the connection secret. |
| connectionSecret.create | bool | `true` | Create the connection secret shell object. |
| connectionSecret.name | string | `""` | Name for the generated connection secret. Defaults to `<release>-<chart>-connection`. |
| domainEndpointOptions | object | `{}` | Custom endpoint, TLS, and HTTPS settings for the domain endpoint. |
| ebsOptions | object | `{}` | EBS volume settings for data nodes in the OpenSearch domain. |
| encryptionAtRestOptions | object | `{}` | Encryption at rest settings for the OpenSearch domain. |
| engineVersion | string | `nil` |  |
| fieldExport | object | `{"enabled":true,"mappings":[{"key":"ENDPOINT","name":"endpoint","path":".status.endpoint"},{"key":"ARN","name":"arn","path":".status.arn"}]}` | FieldExport settings for copying Domain status fields into the connection secret. |
| fieldExport.mappings | list | `[{"key":"ENDPOINT","name":"endpoint","path":".status.endpoint"},{"key":"ARN","name":"arn","path":".status.arn"}]` | Fields exported from Domain status into the generated secret. |
| fullnameOverride | string | `""` |  |
| ipAddressType | string | `nil` |  |
| logPublishingOptions | object | `{}` | Log publishing settings for the OpenSearch domain. |
| name | string | `nil` | OpenSearch domain name from `Domain.spec.name`. |
| nameOverride | string | `""` |  |
| nodeToNodeEncryptionOptions | object | `{}` | Node-to-node encryption settings for the OpenSearch domain. |
| offPeakWindowOptions | object | `{}` | Off-peak maintenance window settings for the OpenSearch domain. |
| pushSecret | object | `{"enabled":false,"name":"","refreshInterval":"1h","sourceKey":"ENDPOINT","storeKind":"SecretStore","target":{"name":"","provider":"","type":"Opaque"}}` | External Secrets PushSecret settings for publishing a selected secret key to an external store. |
| pushSecret.target.name | string | `""` | Remote secret name in the target provider. |
| pushSecret.target.provider | string | `""` | External Secrets store ref name (e.g. aws-secrets-manager). |
| pushSecret.target.type | string | `"Opaque"` | Remote provider-specific secret type/property. |
| reflector | object | `{"allowedNamespaces":[],"enabled":false,"pushNamespaces":[]}` | Secret reflector settings for syncing the connection secret across namespaces. |
| reflector.allowedNamespaces | list | `[]` | Namespaces allowed to pull/reflect this secret. |
| reflector.pushNamespaces | list | `[]` | Namespaces to push reflected secrets into. |
| resourceName | string | `""` | Optional explicit Domain metadata.name. Defaults to the chart fullname. |
| sequencedConnection | object | `{"enabled":false,"kubectlImage":"bitnami/kubectl:latest","maxWaitSeconds":3600,"pollIntervalSeconds":15,"syncWave":20,"ttlSecondsAfterFinished":3600}` | Use Argo hook jobs to create a stable connection secret before sync and patch endpoint data after the Domain becomes ready. |
| sequencedConnection.enabled | bool | `false` | Enable Argo-hooked secret bootstrapping and connection-data syncing. |
| sequencedConnection.kubectlImage | string | `"bitnami/kubectl:latest"` | kubectl image used by the sequencing jobs. |
| sequencedConnection.maxWaitSeconds | int | `3600` | Maximum time to wait for the Domain endpoint to appear. |
| sequencedConnection.pollIntervalSeconds | int | `15` | Poll interval for waiting on the Domain endpoint. |
| sequencedConnection.syncWave | int | `20` | Sync wave used by the post-resource connection sync job. |
| sequencedConnection.ttlSecondsAfterFinished | int | `3600` | TTL for completed sequencing jobs. |
| softwareUpdateOptions | object | `{}` | Software update preferences for the OpenSearch domain. |
| tags | list | `[]` |  |
| vpcOptions | object | `{}` | VPC networking settings for the OpenSearch domain. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
