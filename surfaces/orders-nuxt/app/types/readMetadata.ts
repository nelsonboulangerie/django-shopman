// Additive read metadata. Actions retain their own authoritative revisions.
export interface ReadMetadata {
  generated_at?: string;
  contract_version?: number;
}
