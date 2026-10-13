/**
 * Franja de datos ficticios.
 *
 * Toda vista que use `mock` la muestra de forma visible. No es decorativa:
 * evita que alguien lea una cifra inventada como si fuera información real de
 * talento humano.
 */

import Icon from './Icon'
import { FIXTURE_META } from '../mock'

export default function FixtureNote({ detail }) {
  return (
    <div className="fixture-note" role="note">
      <Icon name="alerta" size={18} />
      <span>
        <strong>{FIXTURE_META.label}.</strong> {FIXTURE_META.note}
        {detail ? <> {detail}</> : null}
      </span>
    </div>
  )
}
