# Restrict application network access

Use `networkPolicy` to allow only the connections an application needs without
maintaining its pod selector in `extraManifests`. The feature is disabled by
default, so upgrading the chart doesn't change existing network access.

## Before enabling it

Confirm that the cluster's network plugin enforces `networking.k8s.io/v1`
NetworkPolicy. Kubernetes accepts policies even when the plugin doesn't enforce
them. You'll need permission to manage NetworkPolicies in the application
namespace and read the namespaces and pod labels used in your rules.

Enabling this policy isolates application pods for both ingress and egress.
With no rules, it permits no connections in either direction beyond Kubernetes'
built-in exceptions, such as replies and traffic from the pod's node. Other
policies selecting the same pods can still allow traffic: NetworkPolicies are
additive, not ordered firewall rules. Check existing policies before rollout.
See the [Kubernetes NetworkPolicy behavior](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Inventory ingress controllers, scrapers, DNS resolvers, and application
dependencies first. Include connections made by init containers and sidecars;
the policy applies to the whole pod. It doesn't select Redis subchart pods or
other application releases, and it doesn't automatically allow access to them.

The example below assumes pod-network ingress controllers and CoreDNS. Check
the actual labels and resolver address in your cluster; these are examples,
not chart defaults. NodeLocal DNS, `hostNetwork` pods, and Service address
translation can need different rules depending on the network plugin. Consult
your plugin's documentation and verify traffic in a test namespace before
rolling this out to production.

## Configure allowed connections

Adapt this complete example and save it as `network-policy-values.yaml`. The
image, domain, and database IP are placeholders; replace them with your
application's values. The app must listen on 8080 and expose metrics on 9090.
The Ingress controller and Prometheus Operator must already be installed for
the Ingress and ServiceMonitor resources to work.

```yaml
image:
  repository: ghcr.io/example/app
  tag: "1.2.3"

service:
  port: 8080

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: app.example.com
      paths:
        - path: /
          pathType: Prefix

serviceMonitor:
  enabled: true
  alternatePort: 9090

networkPolicy:
  enabled: true
  applicationIngress:
    enabled: true
    from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: ingress-nginx
        podSelector:
          matchLabels:
            app.kubernetes.io/component: controller
  dnsEgress:
    enabled: true
    to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
        podSelector:
          matchLabels:
            k8s-app: kube-dns
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app.kubernetes.io/name: prometheus
      ports:
        - port: 9090
          protocol: TCP
  egress:
    - to:
        - ipBlock:
            cidr: 192.0.2.10/32
      ports:
        - port: 5432
          protocol: TCP
```

This adds four exceptions to the policy:

| Traffic | Peer | Destination port |
| --- | --- | --- |
| Application ingress | Controller pods in `ingress-nginx` | Named TCP port `http` (8080 here) |
| DNS egress | DNS pods in `kube-system` | UDP and TCP 53 |
| Metrics ingress | Prometheus pods in `monitoring` | TCP 9090 |
| Database egress | Example external database IP | TCP 5432 |

`applicationIngress` includes the main Service's `http` target and every
`service.extraPorts` target, preserving each protocol. It uses `targetPort`,
falling back to `port` when unset, just as the Service does. A named target
must match a declared container port. The separate metrics Service isn't
included; add its port to `networkPolicy.ingress` as above. If metrics share
the application port, NetworkPolicy cannot distinguish HTTP paths. Keep the
chart's public metrics-blocking Ingress or an equivalent application-level
restriction.

Application ingress and DNS egress are independently disabled by default.
Each helper requires a nonempty peer list when enabled, even with Helm's
`--skip-schema-validation` flag. Turning a helper off
removes its rule; it doesn't remove any equivalent access granted through
additional rules or another policy.

## Add native rules

`networkPolicy.ingress` and `networkPolicy.egress` accept native Kubernetes
rules. List multiple peers for alternatives (OR). Put `namespaceSelector` and
`podSelector` in the same peer when both must match (AND). A `podSelector`
without a namespace selector selects pods only in the application's namespace;
an empty `namespaceSelector` selects all namespaces. An `ipBlock` accepts IPv4
or IPv6 CIDRs and an optional `except` list of strict subnets. It cannot share
a peer with either selector.

An empty rule `{}` allows all traffic in that direction. Within a rule, an
omitted or empty peer list allows any source or destination, and omitted or
empty `ports` allows any port. By contrast, an empty top-level rule list adds
no permissions. An empty peer `{}` is invalid. These distinctions follow the
[Kubernetes NetworkPolicy API](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/network-policy-v1/).

Ports accept integers from 1 to 65535 or Kubernetes port names. `protocol`
accepts `TCP` (the API default), `UDP`, or `SCTP`. An optional `endPort` must be
an integer at least as large as a numeric `port`; named ranges are invalid.
Port ranges require a supporting network plugin. The schema checks structure,
peer combinations, and selector operators; Helm checks reversed port ranges.
Kubernetes still validates CIDR syntax, subnet containment, and label syntax.
This isn't a replacement for server-side validation.

## Render, validate, and roll out

From the repository root, use the pinned Helm version and your deployment
values. The commands below assume the adapted file is in that directory and
the application namespace is `myapp`. Set your Kubernetes context to a test
cluster first. Your deployment identity needs NetworkPolicy create, update,
patch, and delete permissions in that namespace; it needs the chart's usual
resource permissions too.

```bash
helm template myapp charts/universal-chart --namespace myapp \
  -f network-policy-values.yaml \
  --show-only templates/networkpolicy.yaml
kubectl auth can-i create networkpolicies.networking.k8s.io -n myapp
helm template myapp charts/universal-chart --namespace myapp \
  -f network-policy-values.yaml \
  --show-only templates/networkpolicy.yaml |
  kubectl apply --dry-run=server -n myapp -f -
```

The rendered policy should select only this release's application labels and
contain both policy types and the four rules described above. The permission
check should return `yes`, and the server dry run should report validation
success without changing the cluster. Rendering validates configuration, not
packet enforcement.

Deploy through the application's normal Helm or Argo CD workflow in the test
namespace. Confirm that ingress requests and metrics scrapes succeed, and that
the application resolves names and connects to its database. Test both UDP and
TCP DNS if the resolver supports them. Try the same application and metrics
ports from an unselected pod, and an unlisted external destination from the
application pod; those connections should fail. Use destinations known to be
reachable without the policy so a dead endpoint doesn't masquerade as a pass.
An allowed destination pod may need its own ingress rule as well.

Before migrating a policy from `extraManifests`, compare its selectors and
rules with the generated policy. Remove the old resource from its owning
configuration when you adopt the new one. Leaving an old allow-all policy in
place defeats the restriction, and using the same name in both paths produces
duplicate resources.

If a required connection fails, check pod and namespace labels, target ports,
other matching policies, and network-plugin logs. Correct the missing rule and
redeploy. For an urgent rollback, restore the previous release values or set
`networkPolicy.enabled: false` through the normal deployment workflow. Ensure
Argo CD prunes the generated NetworkPolicy if Argo manages it. Removing this
policy can broaden access; other policies may still isolate the pods.
