export interface Controller {
  org: string
  repo: string
  slug: string  // org/repo
  versions: string[]  // sorted newest first
}

export interface Resource {
  kind: string
  group: string
  version: string
  plural: string
  scope: 'Namespaced' | 'Cluster'
  shortNames?: string[]
}

export interface SchemaProperty {
  $ref?: string
  description?: string
  type?: string
  format?: string
  enum?: unknown[]
  required?: string[]
  properties?: Record<string, SchemaProperty>
  items?: SchemaProperty
  additionalProperties?: SchemaProperty | boolean
  'x-kubernetes-preserve-unknown-fields'?: boolean
  'x-kubernetes-int-or-string'?: boolean
  oneOf?: SchemaProperty[]
  anyOf?: SchemaProperty[]
  allOf?: SchemaProperty[]
  default?: unknown
  minimum?: number
  maximum?: number
  pattern?: string
}

export interface VersionDiff {
  added: Resource[]
  removed: Resource[]
  changed: { resource: Resource; addedFields: string[]; removedFields: string[] }[]
}
