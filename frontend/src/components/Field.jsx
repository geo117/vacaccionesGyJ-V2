/**
 * Campo de texto con etiqueta visible, ayuda y error.
 *
 * Reglas aplicadas:
 *  - La etiqueta es un `<label>` real asociado por `htmlFor`: el `placeholder`
 *    nunca sustituye a la etiqueta.
 *  - El error vive junto al campo (`aria-describedby` + `aria-invalid`), no en
 *    un resumen al principio de la página.
 *  - No se valida en cada pulsación: el error aparece cuando el usuario envía o
 *    sale del campo, para no regañar mientras escribe.
 *  - El mensaje de error lleva icono y texto, no sólo color.
 */

import Icon from './Icon'

export default function Field({
  id,
  label,
  type = 'text',
  value,
  onChange,
  onBlur,
  onKeyUp,
  error,
  hint,
  autoComplete,
  inputMode,
  placeholder,
  disabled = false,
  action = null,
  inputRef,
  maxLength,
  required = false,
}) {
  const errorId = `${id}-error`
  const hintId = `${id}-hint`
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>

      <div className="field__control">
        <input
          ref={inputRef}
          id={id}
          name={id}
          type={type}
          className={`field__input${action ? ' field__input--with-action' : ''}`}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          onKeyUp={onKeyUp}
          autoComplete={autoComplete}
          inputMode={inputMode}
          placeholder={placeholder}
          disabled={disabled}
          maxLength={maxLength}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          spellCheck="false"
          autoCapitalize="none"
        />
        {action}
      </div>

      {hint && !error ? (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}

      {error ? (
        <p className="field__error" id={errorId} role="alert">
          <Icon name="error" size={16} />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  )
}
