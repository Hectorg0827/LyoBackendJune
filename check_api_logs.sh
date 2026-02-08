#!/bin/bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lyo-backend AND textPayload:\"API Key Check\"" --limit 20 --format="value(textPayload)"
