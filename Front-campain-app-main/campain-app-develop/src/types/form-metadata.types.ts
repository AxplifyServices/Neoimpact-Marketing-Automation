/**
 * Type definitions for dynamic form metadata
 */

export type FieldType = "Text" | "Numérique" | string[];

export interface ClientFormMetadata {
  [fieldName: string]: FieldType;
}

export interface FormSection {
  id: string;
  label: string;
  fields: string[];
  alwaysExpanded?: boolean;
}
