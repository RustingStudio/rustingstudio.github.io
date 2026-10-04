import { getCollection, type CollectionEntry } from 'astro:content';
import { u, type ProjectId } from '../data/projects';

export type Page = CollectionEntry<'pages'>;
export type Kind = 'docs' | 'tutorials';

/** "engine/docs/getting-started" → "getting-started"; the docs index has no slug. */
export const slugOf = (p: Page) => { const s = p.id.split('/').slice(2).join('/'); return s === 'index' ? undefined : s; };
export const hrefOf = (p: Page) => u(`/${p.data.project}/${p.data.kind}/${slugOf(p) ? slugOf(p) + '/' : ''}`);

/** Pages of one project and kind, in sidebar order. */
export async function pagesOf(project: ProjectId, kind: Kind) {
  const all = await getCollection('pages', (p) => p.data.project === project && p.data.kind === kind);
  return all.sort((a, b) => a.data.order - b.data.order);
}

/** Sidebar groups in first-seen order. */
export function groupsOf(pages: Page[], active?: Page) {
  const groups = new Map<string, { label: string; href: string; active: boolean }[]>();
  for (const p of pages) {
    if (!groups.has(p.data.group)) groups.set(p.data.group, []);
    groups.get(p.data.group)!.push({ label: p.data.title, href: hrefOf(p), active: p.id === active?.id });
  }
  return [...groups].map(([title, links]) => ({ title, links }));
}

export type Post = CollectionEntry<'posts'>;

/** RustingScience posts, newest first. */
export const postsByDate = async () => (await getCollection('posts')).sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf());
export const postHref = (p: Post) => u(`/science/${p.id}/`);
export const postDate = (p: Post) => p.data.date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

/** Sidebar: an "All posts" link, then posts grouped by year. */
export function postGroups(posts: Post[], active?: Post) {
  const years = new Map<string, { label: string; href: string; active: boolean }[]>();
  for (const p of posts) {
    const y = String(p.data.date.getUTCFullYear());
    if (!years.has(y)) years.set(y, []);
    years.get(y)!.push({ label: p.data.title, href: postHref(p), active: p.id === active?.id });
  }
  return [{ title: 'Science', links: [{ label: 'All posts', href: u('/science/'), active: !active }] }, ...[...years].map(([title, links]) => ({ title, links }))];
}
