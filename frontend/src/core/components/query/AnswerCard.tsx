import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createLowlight } from 'lowlight';
import { toText } from 'hast-util-to-text';
import { visit } from 'unist-util-visit';
import type { Root, Element } from 'hast';
import bash from 'highlight.js/lib/languages/bash';
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import powershell from 'highlight.js/lib/languages/powershell';
import sql from 'highlight.js/lib/languages/sql';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import xml from 'highlight.js/lib/languages/xml';
import plaintext from 'highlight.js/lib/languages/plaintext';
import { MessageSquare } from 'lucide-react';

// Custom rehype plugin backed by lowlight/core with only the languages we
// actually see in red-team LLM answers. rehype-highlight (the off-the-shelf
// plugin) imports lowlight's `common` bundle at module scope, so even when
// you pass `languages: {...}` the full common set still ships. This plugin
// uses `createLowlight` directly and registers a ~10-language subset.
// Rollup tree-shakes everything else; saves ~80 KB gzip on the /query chunk.
const lowlight = createLowlight();
lowlight.register({ bash, python, javascript, typescript, powershell, sql, json, yaml, xml, plaintext });
lowlight.registerAlias({
  bash: ['sh', 'shell'],
  python: ['py'],
  javascript: ['js'],
  typescript: ['ts'],
  powershell: ['ps1'],
  yaml: ['yml'],
  xml: ['html'],
});

function rehypeHighlightSlim() {
  return (tree: Root) => {
    visit(tree, 'element', (node: Element, _index, parent) => {
      if (node.tagName !== 'code' || !parent) return;
      const classes = Array.isArray(node.properties?.className) ? (node.properties!.className as string[]) : [];
      const langClass = classes.find((c) => typeof c === 'string' && c.startsWith('language-'));
      if (!langClass) return;
      const lang = langClass.slice('language-'.length);
      if (!lowlight.registered(lang)) return;
      const code = toText(node, { whitespace: 'pre' });
      const fragment = lowlight.highlight(lang, code);
      node.properties = {
        ...node.properties,
        className: ['hljs', ...classes],
      };
      node.children = fragment.children as Element['children'];
    });
  };
}

interface AnswerCardProps {
  answer: string;
}

export default function AnswerCard({ answer }: AnswerCardProps) {
  return (
    <div className="relative bg-gradient-to-br from-gray-800/90 via-gray-800/95 to-gray-900/90 border border-gray-700/50 rounded-xl p-6 shadow-xl">
      {/* Decorative gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 via-transparent to-purple-500/5 rounded-xl pointer-events-none" />
      
      {/* Content */}
      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-4 pb-4 border-b border-gray-700/50">
          <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
            <MessageSquare className="h-5 w-5 text-blue-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Answer</h2>
        </div>
        
        <div className="prose prose-invert prose-lg max-w-none">
          <div className="text-gray-200 leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlightSlim]}
              components={{
                // Custom styling for markdown elements
                h1: ({ node, ...props }) => (
                  <h1 className="text-2xl font-bold text-white mt-6 mb-4 first:mt-0" {...props} />
                ),
                h2: ({ node, ...props }) => (
                  <h2 className="text-xl font-semibold text-white mt-5 mb-3" {...props} />
                ),
                h3: ({ node, ...props }) => (
                  <h3 className="text-lg font-semibold text-gray-100 mt-4 mb-2" {...props} />
                ),
                p: ({ node, ...props }) => (
                  <p className="mb-4 text-gray-200 leading-relaxed" {...props} />
                ),
                ul: ({ node, ...props }) => (
                  <ul className="list-disc list-inside mb-4 space-y-2 text-gray-200" {...props} />
                ),
                ol: ({ node, ...props }) => (
                  <ol className="list-decimal list-inside mb-4 space-y-2 text-gray-200" {...props} />
                ),
                li: ({ node, ...props }) => (
                  <li className="ml-4 text-gray-200" {...props} />
                ),
                code: ({ node, className, children, ...props }: any) => {
                  const isInline = !className;
                  return isInline ? (
                    <code
                      className="px-1.5 py-0.5 bg-gray-900/60 text-blue-300 rounded text-sm font-mono border border-gray-700/50"
                      {...props}
                    >
                      {children}
                    </code>
                  ) : (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  );
                },
                pre: ({ node, ...props }) => (
                  <pre
                    className="bg-gray-900/80 border border-gray-700/50 rounded-lg p-4 overflow-x-auto mb-4"
                    {...props}
                  />
                ),
                blockquote: ({ node, ...props }) => (
                  <blockquote
                    className="border-l-4 border-blue-500/50 pl-4 italic text-gray-300 my-4 bg-gray-900/30 py-2 rounded-r"
                    {...props}
                  />
                ),
                strong: ({ node, ...props }) => (
                  <strong className="font-semibold text-white" {...props} />
                ),
                a: ({ node, ...props }) => (
                  <a
                    className="text-blue-400 hover:text-blue-300 underline"
                    target="_blank"
                    rel="noopener noreferrer"
                    {...props}
                  />
                ),
              }}
            >
              {answer}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}

