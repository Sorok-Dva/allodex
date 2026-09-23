import { Fragment, type ReactNode } from 'react';
import { Link } from '@/lib/router';
import { linkNames, paragraphs, parseMarkdown, refPath } from './lorebook.logic';
import s from './LorebookScreen.module.css';

type Props = {
  text: string;
  markdown?: boolean;
  names?: ReadonlyMap<string, string>;
  /** Référence de l'entrée affichée : jamais liée à elle-même. */
  self?: string;
  /** Cibles déjà liées dans l'entrée (partagé entre les textes : un seul lien par cible). */
  used?: Set<string>;
};

function Inline({ text, names, self, used }: { text: string; names?: ReadonlyMap<string, string>; self?: string; used?: Set<string> }) {
  const segments = names ? linkNames(text, names, self, 5, used) : [{ text }];
  return <>{segments.map((seg, i) => seg.ref ? <Link key={i} to={refPath(seg.ref)} className={s.autoLink}>{seg.text}</Link> : <Fragment key={i}>{seg.text}</Fragment>)}</>;
}

/** Gras et italique Markdown (`**…**`, `*…*`), puis liens automatiques dans chaque morceau. */
function Emphasis({ text, ...rest }: { text: string; names?: ReadonlyMap<string, string>; self?: string; used?: Set<string> }) {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(<Inline key={k++} text={text.slice(last, m.index)} {...rest} />);
    const inner = m[0].replace(/^\*+|\*+$/g, '');
    out.push(m[0].startsWith('**') ? <strong key={k++}><Inline text={inner} {...rest} /></strong> : <em key={k++}><Inline text={inner} {...rest} /></em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(<Inline key={k++} text={text.slice(last)} {...rest} />);
  return <>{out}</>;
}

export function RichText({ text, markdown, names, self, used }: Props) {
  if (markdown) {
    const blocks = parseMarkdown(text);
    const out: ReactNode[] = [];
    let list: ReactNode[] = [];
    const flush = () => { if (list.length) { out.push(<ul key={`u${out.length}`} className={s.mdList}>{list}</ul>); list = []; } };
    blocks.forEach((b, i) => {
      if (b.type === 'li') { list.push(<li key={i}><Emphasis text={b.text} names={names} self={self} used={used} /></li>); return; }
      flush();
      out.push(b.type === 'h'
        ? <h3 key={i} className={s.mdHeading}><Emphasis text={b.text} names={names} self={self} used={used} /></h3>
        : <p key={i}><Emphasis text={b.text} names={names} self={self} used={used} /></p>);
    });
    flush();
    return <div className={s.prose}>{out}</div>;
  }
  return <div className={s.prose}>{paragraphs(text).map((p, i) => <p key={i}><Inline text={p} names={names} self={self} used={used} /></p>)}</div>;
}
