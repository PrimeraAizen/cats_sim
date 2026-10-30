// CI/CD pipeline of the CATS simulator, run by the Jenkins defined in jenkins/.
//
// Every branch: lint and type-check, unit tests with coverage, Docker image build,
//               and a smoke run of the image.
// main only:    push the image to Docker Hub and run it as a Job on Minikube.
//
// Credentials (created by jenkins/casc.yaml): `dockerhub` and `kubeconfig`.

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    environment {
        IMAGE_NAME = 'cats-sim'
        K8S_NAMESPACE = 'cats-sim'
        UV_LINK_MODE = 'copy'
        UV_NO_SYNC = '1'      // `uv run` uses the environment from the "Set up" stage
        UV_NO_PROGRESS = '1'
    }

    stages {
        stage('Set up') {
            steps {
                script {
                    env.IMAGE_TAG = env.GIT_COMMIT.take(8)
                    env.APP_VERSION = sh(script: 'uv version --short', returnStdout: true).trim()
                }
                sh 'uv sync --locked --all-extras'
                echo "cats-sim ${env.APP_VERSION}, commit ${env.GIT_COMMIT}, image tag ${env.IMAGE_TAG}"
            }
        }

        stage('Quality') {
            parallel {
                stage('Lint') {
                    steps {
                        sh 'uv run ruff check . && uv run ruff format --check .'
                    }
                }
                stage('Type-check') {
                    steps {
                        sh 'uv run mypy'
                    }
                }
                stage('Dockerfile lint') {
                    steps {
                        sh 'docker run --rm -i hadolint/hadolint:v2.15.1 < Dockerfile'
                    }
                }
            }
        }

        stage('Unit tests') {
            steps {
                sh '''
                    uv run pytest \
                      --junitxml=reports/junit.xml \
                      --cov --cov-report=term --cov-report=xml:reports/coverage.xml
                '''
            }
            post {
                always {
                    junit testResults: 'reports/junit.xml', allowEmptyResults: true
                    recordCoverage tools: [[parser: 'COBERTURA', pattern: 'reports/coverage.xml']],
                                   sourceDirectories: [[path: 'src']]
                }
            }
        }

        stage('Build image') {
            steps {
                sh '''
                    docker build \
                      --build-arg VERSION="$APP_VERSION" \
                      --build-arg REVISION="$GIT_COMMIT" \
                      --tag "$IMAGE_NAME:$IMAGE_TAG" .
                    docker image ls "$IMAGE_NAME:$IMAGE_TAG"
                '''
            }
        }

        stage('Smoke-test image') {
            steps {
                // Same restrictions as on Kubernetes: read-only root file system, no capabilities.
                sh '''
                    docker run --rm "$IMAGE_NAME:$IMAGE_TAG" --version
                    docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
                      --tmpfs /tmp --tmpfs /results:mode=1777 "$IMAGE_NAME:$IMAGE_TAG"
                '''
            }
        }

        stage('Push to Docker Hub') {
            when { branch 'main' }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'DOCKERHUB_USER',
                                                  passwordVariable: 'DOCKERHUB_TOKEN')]) {
                    // Per-build Docker config, so the login never outlives the build.
                    withEnv(["DOCKER_CONFIG=${env.WORKSPACE}/.docker"]) {
                        sh '''
                            printf '%s' "$DOCKERHUB_TOKEN" | docker login --username "$DOCKERHUB_USER" --password-stdin
                            for tag in "$IMAGE_TAG" latest; do
                                docker tag "$IMAGE_NAME:$IMAGE_TAG" "$DOCKERHUB_USER/$IMAGE_NAME:$tag"
                                docker push "$DOCKERHUB_USER/$IMAGE_NAME:$tag"
                            done
                            docker logout
                        '''
                    }
                    script {
                        env.DEPLOY_IMAGE = "${DOCKERHUB_USER}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                    }
                }
            }
        }

        stage('Deploy to Minikube') {
            when { branch 'main' }
            steps {
                withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        job="cats-sim-smoke-$BUILD_NUMBER"
                        sed -e "s|__JOB_NAME__|$job|" \
                            -e "s|__IMAGE__|docker.io/$DEPLOY_IMAGE|" \
                            -e "s|__VERSION__|$APP_VERSION|" \
                            -e "s|__GIT_COMMIT__|$GIT_COMMIT|" \
                            -e "s|__BUILD_URL__|$BUILD_URL|" \
                            k8s/job.yaml > job.rendered.yaml
                        kubectl apply -f job.rendered.yaml

                        # Wait until the Job has either completed or failed (10 minutes at most).
                        state=""
                        for i in $(seq 120); do
                            state=$(kubectl -n "$K8S_NAMESPACE" get job "$job" \
                                    -o jsonpath='{.status.conditions[?(@.status=="True")].type}')
                            case "$state" in *Complete*|*Failed*) break ;; esac
                            sleep 5
                        done
                        kubectl -n "$K8S_NAMESPACE" get job,pods -l app.kubernetes.io/name=cats-sim
                        kubectl -n "$K8S_NAMESPACE" logs "job/$job" --tail=40 || true
                        case "$state" in
                            *Complete*) echo "Job $job completed on Minikube" ;;
                            *) echo "Job $job did not complete (state: ${state:-timeout})"; exit 1 ;;
                        esac
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**, job.rendered.yaml', allowEmptyArchive: true
            // Remove every local tag of this build's image; the build cache is kept.
            sh '''
                docker image ls -q --filter "label=org.opencontainers.image.revision=$GIT_COMMIT" \
                  | sort -u | xargs -r docker image rm --force || true
            '''
            cleanWs()
        }
    }
}
