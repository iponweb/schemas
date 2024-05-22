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

// See also:
// - https://gateway-api.sigs.k8s.io/reference/spec
var (
	// crdNames correspond to the internal OpenAPI definition names of the
	// CRDs we're interested in. Dependencies do not need to be listed, as
	// they will be calculated on build. The list are the keys of the map
	// returned from the function GetOpenAPIDefinitions at:
	crdNames = []string{
		"sigs.k8s.io/gateway-api/apis/v1.GatewayClass",
		"sigs.k8s.io/gateway-api/apis/v1.Gateway",
		"sigs.k8s.io/gateway-api/apis/v1.HTTPRoute",
		"sigs.k8s.io/gateway-api/apis/v1.GRPCRoute",
		"sigs.k8s.io/gateway-api/apis/v1alpha2.BackendLBPolicy",
		"sigs.k8s.io/gateway-api/apis/v1alpha2.ReferenceGrant",
		"sigs.k8s.io/gateway-api/apis/v1alpha2.TCPRoute",
		"sigs.k8s.io/gateway-api/apis/v1alpha2.TLSRoute",
		"sigs.k8s.io/gateway-api/apis/v1alpha2.UDPRoute",
	}

	hostConversionRules = map[string]string{
		"github.com/kubernetes-sigs/gateway-api": "gateway-api.sigs.k8s.io",
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

func friendlyName(name string) string {
	nameParts := strings.Split(name, "/")
	// Reverse first part. e.g., io.k8s... instead of k8s.io...
	if len(nameParts) > 0 && strings.Contains(nameParts[0], ".") {
		parts := strings.Split(nameParts[0], ".")
		for i, j := 0, len(parts)-1; i < j; i, j = i+1, j-1 {
			parts[i], parts[j] = parts[j], parts[i]
		}
		nameParts[0] = strings.Join(parts, ".")
	}
	return strings.Join(nameParts, ".")
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
				Title:   "kubernetes gateway api CRD OpenAPI",
				Version: "v1.1.0",
			},
		},
		GetDefinitions: definitionGetter,
		GetDefinitionName: func(name string) (string, spec.Extensions) {
			for f, t := range hostConversionRules {
				if strings.HasPrefix(name, f) {
					name = t + name[len(f):]
				}
			}

			return friendlyName(name), nil
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
