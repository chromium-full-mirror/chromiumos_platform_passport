# passport

A service for controlling components in ChromeOS peripheral testbeds.

See go/cros-pass-port

## Building and Running

### Without Docker
#### Local Machine
The executable can be built on your local machine by running `./scripts/build.sh`

The service can be started in `server` mode by running:
```
./go/bin/passport
```

### With Docker
#### Local Machine
The service can be built on your local machine by running `./scripts/build_docker.sh`.
By default this only builds for `amd64`. To include `arm64` use the `--platforms` flag.

If you want to use TOT rather than your local checkout you should add
the `--remote_source` flag to your build command e.g.
```
./scripts/build_docker.sh --platforms=linux/amd64,linux/arm64 --remote_source
```

The container can be started on your local machine by running
```
docker run -p 8200:8300 passport:amd64
```

#### Remote Machine
The service can be started on a remote machine by running `./scripts/docker_on_remote.sh <HOSTNAME>`
If the remote machine is ARM based you should include the `--include-arm` flag.

For a remote satlab device this would look like
```
./scripts/docker_on_remote.sh --include-arm moblab@XXX.XXX.XXX.XXX
```

The script will automatically start the service at port `8300` on the remote machine.

To connect to it locally, you will likely need to forward this port to your local machine.

The `docker_on_remote.sh` will print out an ssh tunnel command that can be used to connect
to the service, the output will look like:
```
$ ./scripts/docker_on_remote.sh moblab@XXX.XXX.XXX.XXX
...
...

==================================================================
Successfully updated passport on host moblab@YYY.YYY.YYY.YYY
SSH COMMAND: ssh -L 8300:1XXX.XXX.XXX.XXX:8300 moblab@YYY.YYY.YYY.YYY
==================================================================
```

## Testing

Once a service is running, it can be verified in a separate terminal by running:
```
./go/bin/passport switches detect
```

This will probe for all components connected to the machine and log them
to STDOUT. This can also be used to check an already running service on a remote
machine by forwarding the remote port to your local machine. The default port is
8300 but a different one can be provided via the `-port` flag e.g.
```
./go/bin/passport switches detect -port 9999
```

Additionally, you can test enabling/disabling specific switches from the command line
using:
```
./go/bin/passport switches enable [-switches SWITCH1,SWITCH2]
./go/bin/passport switches disable [-switches SWITCH1,SWITCH2]
```

If you omit the `-switches` argument then all found switches will be used.


## Deploying Passport Updates

As of 2025-8-31 passport updates must be deployed manually. Before we discuss
how to push a passport update lets talk first about the different versions of
passport.

Passport has several versions that are used:

1.  The scripts and development tools use
    `us-docker.pkg.dev/cros-passport/passport/passport:latest`
2.  Lab runs use `us-docker.pkg.dev/cros-registry/test-services/cros-passport`
    with the tag `staging_cros-passport` for staging configs and
    `prod_cros-passport` for prod configs.

The lab run versions are built from the
`us-docker.pkg.dev/cros-passport/passport/passport:latest` development version.

To update development version simply run:

```bash
./scripts/build_docker.sh --push --remote_source --tag latest
```

Once that has been updated the staging version for the lab should get built and
updated within about an hour. You can see the tagged versions
[here](https://pantheon.corp.google.com/artifacts/docker/cros-registry/us/test-services/cros-passport?inv=1&invt=Ab4OnQ&orgonly=true&project=cros-registry&supportedpurview=organizationId).

The prod version is updated manually ~2 times a week (along with other tools)
but you can ask the
[TSE team](https://moma.corp.google.com/team/1871447779735?hq=type%3Apeople&q=cdelagarza%40google.com)
to do a push if you need it sooner.
