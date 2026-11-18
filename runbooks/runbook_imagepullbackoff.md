# Runbook: Investigating ImagePullBackOff and ErrImagePull

## 1. Overview
`ImagePullBackOff` occurs when Kubernetes attempts to pull a container image from a registry but fails. Kubernetes repeatedly retries with exponential backoff delay.

## 2. Common Symptoms
* `kubectl get pods` shows status `ImagePullBackOff` or `ErrImagePull`.
* Pod never reaches `Running` state; restart count is usually 0.
* Events show `Failed to pull image ...: rpc error: code = NotFound`.

## 3. Investigation Steps
1. **Check Pod Events**:
   Run `get_k8s_events(namespace)` or `describe_pod(pod_name, namespace)`.
   Look for events with reason `Failed` or `ErrImagePull`.
2. **Inspect Container Image Tag**:
   Check the image name and tag in the deployment spec.
   Verify if the tag was recently changed by checking `get_recent_deployments(namespace)` or recent Jenkins builds via `get_build_changes(job, build_number)`.
3. **Verify Registry Authentication**:
   If using a private registry, ensure `imagePullSecrets` is properly configured on the pod or ServiceAccount.

## 4. Remediation / Suggested Fix
* If caused by a typo in the tag, correct the image tag in the deployment manifest or rollout previous revision:
  `kubectl rollout undo deployment/<service-name> -n <namespace>`
* If the Jenkins build failed to push the image, re-run the CI/CD pipeline or push the missing image tag.
