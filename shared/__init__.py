"""
Code shared by every RideFlow service: configuration, security helpers,
the MongoDB connection, authentication dependencies and the HTTP client
used for service-to-service calls.

In a large company this would be published as an internal package. For a
learning project, a shared folder keeps things simple while each service
still runs as its own independent process with its own database.
"""
