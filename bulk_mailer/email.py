from pathlib import Path
from envelope import Envelope

import jinja2
import mistune
import frontmatter

from bulk_mailer import jinja_filter
from bulk_mailer.utils import check_file, merge_dicts

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html2text


class EMailGenerator(object):
    """
    docstring
    """

    DEFAULTHTML_TEMPLATE = r'<html dir="ltr"><head></head><body style="text-align:left; direction:ltr;">{{ content }}</body></html>'

    class JinjaRenderer(object):
        """Supplies functions to render templates with Jinja."""
        __env = jinja2.Environment(
            lstrip_blocks=True,
            trim_blocks=True,
            undefined=jinja2.StrictUndefined,
        )
        __env.filters = merge_dicts(__env.filters, jinja_filter.FILTERS)

        @classmethod
        def render(cls, template, context):
            """Renders a template string with Jinja.

            Args:
                template_string (str): The template string to be rendered
                context (dict): The context used for rendering

            Returns:
                str: The rendered string

            Raises:
                jinja2.UndefinedError: If a variable is undefined
                jinja2.TemplateError: If the template contains an invalid syntax
            """
            try:
                return cls.__env.from_string(template).render(context)
            except jinja2.UndefinedError as e:
                raise jinja2.UndefinedError(f"Undefined variable: {e.message}")
            except jinja2.TemplateError as e:
                raise jinja2.TemplateError(f"Jinja template error: {e.message}")

    class MarkdownRenderer(object):
        """
        docstring
        """
        __markdown_renderer = mistune.Markdown(renderer=mistune.Renderer(escape=False, hard_wrap=True))

        @classmethod
        def render(cls, markdown):
            return cls.__markdown_renderer(markdown)

    @classmethod
    def generate(cls, plaintext_template: str, markdown_template: str, html_template: str, context: dict):
        envelope = Envelope()

        # render markdown content
        extended_context = context.copy()
        if markdown_template:
            markdown_content, extended_context = cls._separate_content_and_metadata(markdown_template, context)
            markdown_content = cls.JinjaRenderer.render(markdown_content, extended_context)
            extended_context["content"] = cls.MarkdownRenderer.render(markdown_content)
            html_template = html_template or DEFAULTHTML_TEMPLATE

        # render html content
        if html_template:
            html_content, extended_context = cls._separate_content_and_metadata(html_template, extended_context)
            html_content = cls.JinjaRenderer.render(html_content, extended_context)
            envelope.message(html_content, alternative="html")

        sender = extended_context.get("sender", None)
        recipient = extended_context.get("recipient", None)
        subject = extended_context.get("subject", "")
        
        if plaintext_template:
            # render plaintext content
            plaintext_content, extended_context = cls._separate_content_and_metadata(plaintext_template, context)
            plaintext_content = cls.JinjaRenderer.render(plaintext_content, extended_context)
        else:
            # generate plaintext from html
            html_to_text_converter = html2text.HTML2Text()
            html_to_text_converter.ignore_images = True
            plaintext_content = html_to_text_converter.handle(html_content)

        envelope.message(plaintext_content, alternative="plain")
        sender = sender or extended_context.get("sender", None)
        recipient = recipient or extended_context.get("recipient", None)
        subject = subject or extended_context.get("subject", "")
        if not sender:
            raise Exception("Missing sender")
        envelope.from_(sender).to(recipient).subject(subject)
        return envelope

    @classmethod
    def _separate_content_and_metadata(cls, template, context):
        if not template:
            return ("", context)

        metadata, content = frontmatter.parse(template)

        # render any Jinja content in the metadata
        for key in metadata.keys():
            if isinstance(metadata[key], str):
                metadata[key] = cls.JinjaRenderer.render(metadata[key], context)
        if "from" in metadata and "sender" not in metadata:
            metadata["sender"] = metadata["from"]
        extended_context = merge_dicts(metadata, context)

        return (content, extended_context)