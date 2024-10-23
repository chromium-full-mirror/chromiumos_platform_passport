# passport

A service for controlling components in ChromeOS peripheral testbeds.

See go/cros-pass-port

## Building

### Without Docker
#### Local Machine
The executable can be built on your local machine by running `./scripts/build.sh`

## Testing
When not using docker, the service can be started in `server` mode by running:
```
./go/bin/passport
```

Once a service is running, it can be verified in a separate terminal by running:
```
./go/bin/passport -mode DETECT
```

This will probe for all components connected to the machine and log them
to STDOUT. This can also be used to check an already running service on a remote
machine.

It's also possible to quickly test the executable without starting two separate
processes by running:
```
./go/bin/passport -mode TEST
```

This will perform the same actions as `DETECT` except both the client and server
will be started in the same process without needing a separate terminal window.
