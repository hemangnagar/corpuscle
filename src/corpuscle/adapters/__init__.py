"""Adapters: turn a source into documents with a validated provenance envelope.

An adapter yields dicts with 'envelope' (validated) and, where text is available, 'text'.
Everything the provenance family measures comes from the envelope; what an adapter does not
capture at ingest is lost, so adapters are the place to be thorough.
"""
