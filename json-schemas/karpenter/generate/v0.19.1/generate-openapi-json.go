package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"strings"

	generated "openapi-json-gen/generated/openapi"

	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apiserver/pkg/endpoints/openapi"
	"k8s.io/kube-openapi/pkg/builder"
	"k8s.io/kube-openapi/pkg/common"
	"k8s.io/kube-openapi/pkg/validation/spec"
)

const (
	kubernetesSwaggerUrl = "https://raw.githubusercontent.com/kubernetes/kubernetes/v1.25.2/api/openapi-spec/swagger.json"
)

var (
	// crdNames correspond to the internal OpenAPI definition names of the
	// CRDs we're interested in. Dependencies do not need to be listed, as
	// they will be calculated on build. The list are the keys of the map
	// returned from the function GetOpenAPIDefinitions at:
	crdNames = []string{
		"github.com/aws/karpenter/pkg/apis/v1alpha1.AWSNodeTemplate",
		"github.com/aws/karpenter/pkg/apis/v1alpha5.Provisioner",
	}

	hostConversionRules = map[string]string{
		"github.com/aws/karpenter-core": "core.karpenter.sh",
		"github.com/aws/karpenter":      "karpenter.sh",
	}
)

func reverse[T comparable](input []T) []T {
	var output []T

	for i := len(input) - 1; i >= 0; i-- {
		output = append(output, input[i])
	}

	return output
}

func loadVanilla() spec.Swagger {
	// Get the data
	response, err := http.Get(kubernetesSwaggerUrl)
	if err != nil {
		log.Fatalf("cannot open swagger.json: %+v", err)
	}
	defer response.Body.Close()

	rawSchema, err := ioutil.ReadAll(response.Body)
	if err != nil {
		log.Fatalf("cannot read swagger.json: %+v", err)
	}

	var schema spec.Swagger
	if err := json.Unmarshal(rawSchema, &schema); err != nil {
		log.Fatalf("cannot unmarshal swagger.json: %+v", err)
	}
	return schema
}

func main() {
	// load the swagger.json from kubernetes, which we're using here as a hack
	// to provide any references not already included by openapi-gen in the
	// monitoring.v1 API group.
	vanilla := loadVanilla()

	// use the same naming scheme that kubernetes uses, i.e., reverse domain
	// group, followed by version, then kind
	namer := openapi.NewDefinitionNamer(runtime.NewScheme())

	// construct a getter that uses monitoring.v1 as the primary definition,
	// falling back onto vanilla definitions
	definitionGetter := mergedDefinitions(generated.GetOpenAPIDefinitions, vanilla.Definitions, namer)

	cfg := &common.Config{
		Info: &spec.Info{
			InfoProps: spec.InfoProps{
				Title:   "karpenter CRD OpenAPI",
				Version: "v1",
			},
		},
		GetDefinitions: definitionGetter,
		GetDefinitionName: func(name string) (string, spec.Extensions) {
			for f, t := range hostConversionRules {
				if strings.HasPrefix(name, f) {
					name = t + name[len(f):]
				}
			}

			hostname := name[:strings.Index(name, "/")]
			path := name[strings.Index(name, "/")+1:]

			definitionName := fmt.Sprintf("%s.%s",
				strings.Join(reverse(strings.Split(hostname, ".")), "."),
				strings.Replace(path, "/", ".", -1),
			)
			return definitionName, nil
		},
	}

	// generate swagger for our CRD names
	swag, err := builder.BuildOpenAPIDefinitionsForResources(cfg, crdNames...)
	if err != nil {
		log.Fatalf("cannot build openapi definitions: %+v", err)
	}

	// reëmit the new schema as json
	j, err := json.MarshalIndent(swag, "", "  ")
	if err != nil {
		log.Fatalf("cannot marshal: %+v", err)
	}
	fmt.Println(string(j))
}

func mergedDefinitions(primary common.GetOpenAPIDefinitions, fallback spec.Definitions, namer *openapi.DefinitionNamer) common.GetOpenAPIDefinitions {
	all := map[string]common.OpenAPIDefinition{}
	return func(ref common.ReferenceCallback) map[string]common.OpenAPIDefinition {
		// This allows us to insert extra logic during callback processing,
		// by inserting the schema from the fallback into "all". Technically
		// not fully correct, because if the schema in question doesn't exist
		// in fallback, we continue anyway and hope that the primary definition
		// will have provided the schema (it would error out if not the case).
		ref2 := func(name string) spec.Ref {
			if _, ok := all[name]; !ok {
				stdName, _ := namer.GetDefinitionName(name)
				if v, ok2 := fallback[stdName]; ok2 {
					all[name] = common.OpenAPIDefinition{
						Schema: v,
					}
				}
			}
			return ref(name)
		}
		// Copy whatever primary schemas as-is. References are resolved
		// during this primary(ref2) call.
		//
		// Doing the operations in this order does mean that only referenced
		// schemas from the fallback will be included in the final output.
		for k, v := range primary(ref2) {
			all[k] = v
		}
		return all
	}
}
