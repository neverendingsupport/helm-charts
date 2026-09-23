# Enable the restricted security profile

Use this guide to migrate an existing Linux application to
`securityProfile.enabled: true`. The profile is disabled by default, so you
can opt in one application at a time. Changing the pod security settings
causes a Deployment rollout.

## Check the images first

Check the main image and every init image with the application owner before
changing values. Each must run under a nonzero numeric UID, work without
Linux capabilities, and tolerate the container runtime's default seccomp
filter. Startup scripts that switch users, change ownership, or install
packages often need an image change first.

An image with a numeric non-root `USER` can use the profile directly. If the
image declares a username, or defaults to root but supports another user, set
`podSecurityContext.runAsUser` to the UID the image supports. The chart does
not pick a UID or inspect the image. Kubernetes refuses to start a container
when it cannot verify non-root execution with `runAsNonRoot: true`.

The profile targets the chart's Deployment, including its init containers.
It does not configure the Redis dependency or workloads supplied through
`extraManifests`. Admission webhooks may also inject containers; inspect the
live pod after admission to check their settings.

## Enable the baseline

Add this excerpt to the application's existing values. Keep its image and
other settings:

```yaml
securityProfile:
  enabled: true
```

These are the defaults applied by the profile:

| Setting | Value | Applies to |
| --- | --- | --- |
| `runAsNonRoot` | `true` | Pod, inherited by containers |
| `seccompProfile.type` | `RuntimeDefault` | Pod, inherited by containers |
| `allowPrivilegeEscalation` | `false` | Main and init containers |
| `capabilities.drop` | `[ALL]` | Main and init containers |
| `automountServiceAccountToken` | `false` | Pod and generated ServiceAccount |

Explicit `podSecurityContext` and `securityContext` values merge over these
defaults. Nested maps merge; explicit scalar values and lists replace the
corresponding defaults, including `false` and empty lists. An empty context
uses the baseline. The shared container context applies to the main and init
containers. With the profile enabled, a container's
`extraContainerProps.securityContext` merges last, so it can override a shared
field without discarding the other restrictions. The main container's extra
properties do not apply to init containers.

Overrides can relax restrictions. For example, `securityContext.runAsNonRoot:
false` overrides the pod's non-root setting for the main and init containers.
Namespaces that enforce the
[Restricted Pod Security Standard](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
may reject such exceptions. The profile supplies defaults; it does not enforce
that standard or validate every Kubernetes security-context field.

## Provide writable paths

The profile leaves root filesystems writable. To make them read-only, first
identify every path each image writes to. Mount a writable volume at each
path, and ensure the selected UID or group can write there. This values
excerpt assumes both images support UID and GID `10001`, and only need `/tmp`
for temporary files:

```yaml
securityProfile:
  enabled: true
podSecurityContext:
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
securityContext:
  readOnlyRootFilesystem: true
volumes:
  - name: tmp
    emptyDir: {}
volumeMounts:
  - name: tmp
    mountPath: /tmp
```

Merge these entries with existing volumes and mounts; Helm replaces lists
when values files override them. Mounting a volume hides files already at
that image path. `emptyDir` lasts only for the pod's lifetime and is not
persistent application storage. Main and init containers share these mounts.

## Keep API access only where needed

For chart-created accounts, `serviceAccount.automount: null` selects `true`
without the profile and `false` with it; an explicit boolean wins. With the
profile enabled, the resolved value is also written to the pod, including
when it uses an existing account. With the profile disabled and
`serviceAccount.create: false`, the chart leaves token policy unchanged.
If an existing values file contains `automount: true`, remove that entry or
set it to `null` to adopt the profile default.

An application that calls the Kubernetes API can re-enable token mounting:

```yaml
serviceAccount:
  automount: true
```

With the profile enabled, this choice is set on the pod as well as any
chart-created ServiceAccount. It therefore also works with
`serviceAccount.create: false` and an existing `serviceAccount.name`.
With the profile disabled, the chart retains its previous behavior: automount
is set only on the generated account, and an externally managed account keeps
its own policy. An explicit pod setting takes precedence over the account's
setting in Kubernetes.

Mounting credentials does not grant permissions. Use a dedicated account
bound to only the resources and verbs the application needs; the chart does
not create Role or RoleBinding resources. A `403` response usually means the
account lacks permission, while missing credentials or `401` requires checking
the client's authentication. Disabling automount does not remove explicitly
projected tokens or credentials injected by other controllers.

Follow Kubernetes' [RoleBinding example](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#rolebinding-and-clusterrolebinding)
to bind an app-owned Role to the account. Use only the resources and verbs
the app needs. An operator allowed to impersonate service accounts can check
one permission with the following command. Set `APP_NAMESPACE` to the target
namespace, `APP_SERVICE_ACCOUNT` to the account name, and `APP_VERB` and
`APP_RESOURCE` to one required API operation, such as `get` and `configmaps`:

```bash
kubectl auth can-i "$APP_VERB" "$APP_RESOURCE" \
  --namespace "$APP_NAMESPACE" \
  --as "system:serviceaccount:$APP_NAMESPACE:$APP_SERVICE_ACCOUNT"
```

Expect `yes` for the required operation. Check an operation the app should
not have as well; expect `no`. This verifies authorization, not whether the
pod has usable credentials. If impersonation is forbidden, ask the cluster
operator to run the check.

## Verify and roll out

From the repository root, use the repo-pinned Helm version and your complete
application values in a local `app-values.yaml`. Build the chart dependencies
if they are not already present, then render:

```bash
helm dependency build charts/universal-chart
helm lint charts/universal-chart -f app-values.yaml
helm template app charts/universal-chart -f app-values.yaml
```

Lint must pass. In the rendered Deployment, check pod token mounting and
security context, then check the main and each init container's context.
Rendering proves the fields are present; it cannot prove image compatibility.

Roll out first in a test environment through the application's existing
Argo CD workflow. Use `kubectl` with access to that cluster and namespace.
Set `APP_NAMESPACE` and `APP_DEPLOYMENT` to the actual names before running:

```bash
kubectl -n "$APP_NAMESPACE" rollout status deployment/"$APP_DEPLOYMENT" --timeout=5m
kubectl -n "$APP_NAMESPACE" get deployment "$APP_DEPLOYMENT" -o yaml
kubectl -n "$APP_NAMESPACE" get pods -o yaml
kubectl -n "$APP_NAMESPACE" get events --sort-by=.metadata.creationTimestamp
```

Expect all desired replicas to become available and readiness checks to pass.
Inspect the application's pods for the security fields after admission and
test an ordinary application request. Check init and application logs if a
container fails: UID verification errors need an image or UID correction,
permission errors need ownership or mount changes, and read-only filesystem
errors identify a missing writable path.

To roll back, restore the previous application values in Git and sync Argo CD.
Disabling the profile alone does not remove explicit security-context or
automount overrides added during migration. Restore those too when they caused
the failure, then verify the Deployment becomes available again.

## Upgrade an existing Helm CLI release

Plain `helm upgrade --reuse-values` can retain the previous chart's computed
defaults, including its implicit `serviceAccount.automount: true`. When you
enable the profile, that old `true` is indistinguishable from an explicit
override. It can enable token mounting even if an existing ServiceAccount
has disabled it. The missing profile block in an old release is treated as
disabled, so an upgrade without opting in keeps the old behavior.

For a Helm CLI release, use `--reset-then-reuse-values` to adopt the new chart
defaults while retaining values supplied by the operator. From the repository
root, set `APP_RELEASE` and `APP_NAMESPACE` to the existing release and
namespace. Use the repo-pinned Helm version, cluster credentials with upgrade access,
and the image checks above before running this command; it changes the release
and starts a rollout:

```bash
helm upgrade "$APP_RELEASE" charts/universal-chart \
  --namespace "$APP_NAMESPACE" \
  --reset-then-reuse-values \
  --set securityProfile.enabled=true
```

That flag does not erase an operator-supplied `automount: true`. To disable
token mounting deliberately during this upgrade, append
`--set serviceAccount.automount=null`. Clearing that value also works if you
must use `--reuse-values`. Verify the rendered and live pod token field is
`false` and follow the rollout checks above. For a CLI-managed release,
`helm history` identifies the previous revision; use `helm rollback` to that
revision if the application fails the migration checks.

Argo CD renders the chart from its configured values files, so it does not
use Helm's release-value reuse flags. Remove old explicit overrides from
those files as described above.

See Kubernetes' [security context guide](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
and [service account guide](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
for the underlying inheritance and token behavior.
