import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

// Written by scripts/sync-content.mjs from the project repositories.
const pages = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/pages' }),
  schema: z.object({
    title: z.string(),
    project: z.enum(['engine', 'brain', 'shader', 'strata', 'rpu']),
    kind: z.enum(['docs', 'tutorials']),
    group: z.string(),
    order: z.number(),
    description: z.string(),
    source: z.string().url(),
    minutes: z.number().optional(),
  }),
});

// RustingScience posts, written by the same script.
const posts = defineCollection({
  loader: glob({ pattern: '*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    description: z.string(),
    tags: z.array(z.string()).default([]),
    project: z.enum(['engine', 'brain', 'shader', 'strata', 'rpu']).optional(),
    minutes: z.number(),
    source: z.string().url(),
  }),
});

export const collections = { pages, posts };
