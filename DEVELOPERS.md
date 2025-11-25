# Developing on this repo

# Danny

Docs are generated with helm-docs.  Just run `helm-docs` at the root of the directory and it'll work.

Schemas are generated with helm-schema.  Run `helm-schema -k required` to regenerate the schema, as the default behavior is to assume everything is required.  Perhaps this should be revisited, though.


# Andre
```
helm template --dry-run --debug \
    -n nes-dev \
    -f /Users/narfdre/Code/herodevs/monorepo/packages/registry/k8s/v2-dev.yaml \
    registry \
    /Users/narfdre/Code/herodevs/helm-charts/charts/nes-node-web \
    --version 0.1.10 \
    --set version=9.9.9 \
    --set secrets.lane=dev \
    --set clusterZone=demo.nes.herodevs.io \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-dev
```


### Dave's old trash
How I was testing last:
```
helm upgrade --install --dry-run \
    -n nes-dev \
    -f /Users/welch/Code/herodevs/nes/packages/api1/k8s/dev.yaml \
    api1 \
    /Users/welch/Code/herodevs/helm-charts/charts/nes-node-web \
    --version 0.1.5 \
    --set version=0.0.8 \
    --set host=api.dev.nes.herodevs.com \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-dev
```


Diffing what's out there from the test:
```
helm get all api1 -n nes-dev > /tmp/nes_deployed.yaml
helm upgrade --install --dry-run \
    -n nes-dev \
    -f /Users/welch/Code/herodevs/nes/packages/api1/k8s/dev.yaml \
    api1 \
    /Users/welch/Code/herodevs/helm-charts/charts/nes-node-web \
    --version 0.1.7 \
    --set version=0.0.8 \
    --set host=api.dev.nes.herodevs.com \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-dev > /tmp/nes_proposed.yaml

diff /tmp/nes_deployed.yaml /tmp/nes_proposed.yaml
```


Debugging a container image locally (with compose running0):
```
 DOCKER_BUILDKIT=1 docker run -it --rm --privileged \
  --network nes_default \
  -v $(pwd)/.env.docker:/home/node/app/.env \
  -v $(pwd):/dockerhost \
  -p '127.0.0.1:3000:3000' \
  "ghcr.io/neverendingsupport/api1:0.0.8" \
  /bin/bash
```

Dry-run / Hot-deploying to dev with test changes:
```
helm upgrade --install \
    -n nes-dev \
    -f /Users/welch/Code/herodevs/nes/packages/api1/k8s/dev.yaml \
    api1 \
    /Users/welch/Code/herodevs/helm-charts/charts/nes-node-web \
    --version 0.1.5 \
    --set replicaCount=5 \
    --set version=0.0.8 \
    --set host=api.dev.nes.herodevs.com \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-dev
```


Dev Deployment invocation:
```
helm repo update nes
helm upgrade --install \
    -n nes-dev \
    -f /Users/welch/Code/herodevs/nes/packages/api1/k8s/dev.yaml \
    api1 \
    nes/nes-node-web \
    --version 0.1.5 \
    --set version=0.0.8 \
    --set host=api.dev.nes.herodevs.com \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-dev
```

Prod Deployment invocation
```
helm repo update nes
helm upgrade --install \
    -n nes-prod \
    -f /Users/welch/Code/herodevs/nes/packages/api1/k8s/prod.yaml \
    api1 \
    nes/nes-node-web \
    --version 0.1.5 \
    --set version=0.0.8 \
    --set host=api.nes.herodevs.com \
    --set imagePullSecret=ghcr-login-secret \
    --set release=nes-prod
```
