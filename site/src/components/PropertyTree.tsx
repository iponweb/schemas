import { useState } from 'react'
import type { SchemaProperty } from '../lib/types'

type Definitions = Record<string, SchemaProperty>

// ── Props ────────────────────────────────────────────────────────────────────

interface PropertyTreeProps {
  schema: SchemaProperty
  name?: string
  definitions?: Definitions
}

interface NodeProps {
  name: string
  schema: SchemaProperty
  depth: number
  isRequired: boolean
  parentRequired?: string[]
  definitions?: Definitions
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Resolve a $ref like "#/definitions/io.k8s.api.core.v1.PodSpec" against the definitions map. */
function resolveRef(schema: SchemaProperty, definitions: Definitions): SchemaProperty {
  if (!schema.$ref) return schema
  const key = schema.$ref.replace('#/definitions/', '')
  const resolved = definitions[key]
  if (!resolved) return schema
  return schema.description ? { ...resolved, description: schema.description } : resolved
}

function getType(schema: SchemaProperty): string {
  if (schema['x-kubernetes-int-or-string']) return 'int-or-string'
  if (schema['x-kubernetes-preserve-unknown-fields']) return 'any'
  if (schema.type) return schema.type
  if (schema.oneOf || schema.anyOf) return 'oneOf'
  if (schema.allOf) return 'allOf'
  return 'object'
}

type TypeColor =
  | 'string' | 'integer' | 'number' | 'boolean'
  | 'object' | 'array' | 'int-or-string' | 'any' | 'oneOf' | 'allOf'

const TYPE_COLORS: Record<TypeColor, string> = {
  string: 'bg-sky-100 text-sky-700',
  integer: 'bg-amber-100 text-amber-700',
  number: 'bg-amber-100 text-amber-700',
  boolean: 'bg-emerald-100 text-emerald-700',
  object: 'bg-violet-100 text-violet-700',
  array: 'bg-indigo-100 text-indigo-700',
  'int-or-string': 'bg-orange-100 text-orange-700',
  any: 'bg-zinc-100 text-zinc-600',
  oneOf: 'bg-purple-100 text-purple-700',
  allOf: 'bg-pink-100 text-pink-700',
}

function TypeBadge({ type }: { type: string }) {
  const color = TYPE_COLORS[type as TypeColor] ?? 'bg-zinc-100 text-zinc-600'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium font-mono ${color}`}>
      {type}
    </span>
  )
}

function hasChildren(schema: SchemaProperty, definitions: Definitions): boolean {
  const type = getType(schema)
  if (type === 'object' && schema.properties && Object.keys(schema.properties).length > 0) return true
  if (type === 'array' && schema.items && typeof schema.items === 'object') {
    const items = resolveRef(schema.items as SchemaProperty, definitions)
    if (items.properties && Object.keys(items.properties).length > 0) return true
  }
  return false
}

// ── Node ─────────────────────────────────────────────────────────────────────

function PropertyNode({ name, schema: rawSchema, depth, isRequired, definitions = {} }: NodeProps) {
  const schema = resolveRef(rawSchema, definitions)
  const [expanded, setExpanded] = useState(
    name === 'metadata' ? false : name === 'spec' ? true : depth < 2
  )
  const [descExpanded, setDescExpanded] = useState(false)

  const type = getType(schema)
  const canExpand = hasChildren(schema, definitions)

  const description = schema.description ?? ''
  const shortDesc = description.length > 120 ? description.slice(0, 120) + '…' : description
  const hasLongDesc = description.length > 120

  let children: Array<{ name: string; schema: SchemaProperty }> = []
  let childRequired: string[] = []

  if (type === 'object' && schema.properties) {
    children = Object.entries(schema.properties).map(([k, v]) => ({ name: k, schema: v }))
    childRequired = schema.required ?? []
  } else if (type === 'array' && schema.items && typeof schema.items === 'object') {
    const items = resolveRef(schema.items as SchemaProperty, definitions)
    if (items.properties) {
      children = Object.entries(items.properties).map(([k, v]) => ({ name: k, schema: v }))
      childRequired = items.required ?? []
    }
  }

  const indentStyle = { paddingLeft: `${depth * 20}px` }

  return (
    <div className="font-mono text-sm">
      <div
        className={`flex items-start gap-2 py-1.5 px-2 rounded-lg group transition-colors
          ${canExpand ? 'cursor-pointer' : 'cursor-default'}
          ${depth === 0 ? 'hover:bg-violet-50' : 'hover:bg-zinc-50'}
        `}
        style={indentStyle}
        onClick={() => canExpand && setExpanded(e => !e)}
      >
        {/* Field info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`font-semibold ${isRequired ? 'text-violet-700' : 'text-zinc-700'} ${depth === 0 ? 'text-base' : 'text-sm'}`}>
              {name}
              {isRequired && <span className="text-red-500 ml-0.5 font-bold">*</span>}
            </span>
            <TypeBadge type={type} />
            {schema.format && (
              <span className="text-xs text-zinc-400 bg-zinc-50 border border-zinc-200 px-1.5 py-0.5 rounded">
                {schema.format}
              </span>
            )}
            {schema.enum && (
              <span className="text-xs text-zinc-400">enum({schema.enum.length})</span>
            )}
            {schema['x-kubernetes-preserve-unknown-fields'] && (
              <span className="text-xs text-zinc-400 italic">free-form</span>
            )}
            {canExpand && (
              <span className="text-xs text-zinc-400 font-mono select-none">
                {expanded ? '−' : '+'}
              </span>
            )}
          </div>

          {description && (
            <div className="mt-1 text-xs text-zinc-500 leading-relaxed">
              <span style={{ fontFamily: 'var(--font-sans, system-ui)' }}>
                {descExpanded ? description : shortDesc}
              </span>
              {hasLongDesc && (
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); setDescExpanded(d => !d) }}
                  className="ml-1 text-violet-500 hover:text-violet-700 transition-colors"
                >
                  {descExpanded ? 'less' : 'more'}
                </button>
              )}
            </div>
          )}

          {schema.default !== undefined && (
            <div className="mt-0.5 text-xs text-zinc-400">
              default:{' '}
              <code className="bg-zinc-100 px-1 py-0.5 rounded text-zinc-600">
                {JSON.stringify(schema.default)}
              </code>
            </div>
          )}

          {schema.pattern && (
            <div className="mt-0.5 text-xs text-zinc-400">
              pattern:{' '}
              <code className="bg-zinc-100 px-1 py-0.5 rounded text-zinc-600 break-all">
                {schema.pattern}
              </code>
            </div>
          )}

          {(schema.minimum !== undefined || schema.maximum !== undefined) && (
            <div className="mt-0.5 text-xs text-zinc-400">
              {schema.minimum !== undefined && <>min: {schema.minimum}</>}
              {schema.minimum !== undefined && schema.maximum !== undefined && ', '}
              {schema.maximum !== undefined && <>max: {schema.maximum}</>}
            </div>
          )}
        </div>
      </div>

      {/* Children */}
      {canExpand && expanded && children.length > 0 && (
        <div className="relative">
          {children.map(child => (
            <div key={child.name} className="relative">
              <PropertyNode
                name={child.name}
                schema={child.schema}
                depth={depth + 1}
                isRequired={childRequired.includes(child.name)}
                parentRequired={childRequired}
                definitions={definitions}
              />
              {/* Bulb — after PropertyNode so it paints on top of hover bg */}
              <div
                className="absolute w-1.5 h-1.5 rounded-full bg-zinc-200 ring-2 ring-white pointer-events-none"
                style={{ left: `${depth * 20 + 4}px`, top: '13px' }}
              />
            </div>
          ))}
          {type === 'array' && schema.items && typeof schema.items === 'object' && !(schema.items as SchemaProperty).properties && (
            <div
              className="py-1.5 px-2 text-xs text-zinc-400 italic"
              style={{ paddingLeft: `${(depth + 1) * 20}px` }}
            >
              items: <TypeBadge type={getType(schema.items as SchemaProperty)} />
            </div>
          )}
          {/* Vertical guide line — last in DOM so it paints on top of all child hover bgs */}
          <div
            className="absolute top-0 bottom-0 w-px bg-zinc-200 rounded-full pointer-events-none"
            style={{ left: `${depth * 20 + 7}px` }}
          />
        </div>
      )}
    </div>
  )
}

// ── Root ─────────────────────────────────────────────────────────────────────

const TOP_FIELDS = ['apiVersion', 'kind', 'metadata']

export default function PropertyTree({ schema, name = 'root', definitions = {} }: PropertyTreeProps) {
  const allProperties = schema.properties ? Object.entries(schema.properties) : []
  const topProperties = [
    ...allProperties.filter(([k]) => TOP_FIELDS.includes(k)).sort(([a], [b]) => TOP_FIELDS.indexOf(a) - TOP_FIELDS.indexOf(b)),
    ...allProperties.filter(([k]) => !TOP_FIELDS.includes(k)),
  ]
  const required = schema.required ?? []

  if (topProperties.length === 0) {
    return (
      <div className="text-sm text-zinc-400 italic py-4 text-center">
        No properties defined
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      {topProperties.map(([propName, propSchema]) => (
        <PropertyNode
          key={propName}
          name={propName}
          schema={propSchema}
          depth={0}
          isRequired={required.includes(propName)}
          parentRequired={required}
          definitions={definitions}
        />
      ))}
    </div>
  )
}
