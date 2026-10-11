// Platoon 5 Digital Album -- lightweight front-end helpers.
// No frameworks; keeps mobile page-weight low. Every interactive feature
// here has a working non-JS fallback (plain form POST + redirect), so
// nothing on the site *requires* JavaScript to function -- this file only
// makes things feel smoother when it's available.

document.addEventListener("DOMContentLoaded", function () {
  // Confirm destructive actions (delete/suspend/etc.)
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("submit", function (e) {
      const message = el.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(message)) {
        e.preventDefault();
      }
    });
  });

  // Auto-dismiss flash alerts after 6 seconds
  document.querySelectorAll(".alert.alert-dismissible").forEach(function (alertEl) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
      bsAlert.close();
    }, 6000);
  });

  // Live character counters for textareas with data-maxlength
  document.querySelectorAll("textarea[data-maxlength]").forEach(function (ta) {
    const max = parseInt(ta.getAttribute("data-maxlength"), 10);
    const counter = document.createElement("div");
    counter.className = "form-text text-end";
    ta.insertAdjacentElement("afterend", counter);
    const update = () => {
      counter.textContent = `${ta.value.length} / ${max}`;
    };
    ta.addEventListener("input", update);
    update();
  });

  initFeedInteractions();
});

const REACTION_EMOJI = { like: "👍", love: "❤️", celebrate: "🎉", support: "🤝" };

function csrfFrom(form) {
  const el = form.querySelector('input[name="csrf_token"]');
  return el ? el.value : "";
}

function updateReactionButton(article, reactionType) {
  const btn = article.querySelector(".js-react-btn");
  if (!btn) return;
  btn.classList.remove("reacted", "reaction-like", "reaction-love", "reaction-celebrate", "reaction-support");
  const icon = btn.querySelector("i");
  if (reactionType) {
    btn.classList.add("reacted", "reaction-" + reactionType);
    btn.innerHTML = `<span style="font-size:1rem;">${REACTION_EMOJI[reactionType]}</span> ${reactionType.charAt(0).toUpperCase() + reactionType.slice(1)}`;
  } else {
    btn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> React';
  }
}

function initFeedInteractions() {
  // Main "React" button: toggles your current/default reaction.
  document.querySelectorAll(".js-react-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      submitReaction(form, form.querySelector('input[name="reaction_type"]').value);
    });
  });

  // Emoji picker options: react with a specific type.
  document.querySelectorAll(".js-react-option").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const article = document.getElementById("announcement-" + btn.dataset.announcement);
      const form = article.querySelector(".js-react-form");
      submitReaction(form, btn.dataset.reaction);
    });
  });

  // "Comment" button focuses the comment input for that post.
  document.querySelectorAll(".js-focus-comment").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const article = document.getElementById("announcement-" + btn.dataset.announcement);
      const input = article.querySelector(".p5-comment-form input[name='body']");
      if (input) input.focus();
    });
  });

  // Comment form: submit via fetch and append the new comment inline.
  document.querySelectorAll(".js-comment-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const input = form.querySelector('input[name="body"]');
      const body = input.value.trim();
      if (!body) return;

      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams({ csrf_token: csrfFrom(form), body: body }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) return;
          const bubble = document.createElement("div");
          bubble.className = "p5-comment";
          bubble.innerHTML = `<i class="fa-solid fa-circle-user fa-lg text-muted"></i>
            <div class="p5-comment-bubble">
              <span class="p5-comment-author">${escapeHtml(data.comment.author)}<span class="p5-comment-time">${data.comment.created_at}</span></span>
              ${escapeHtml(data.comment.body)}
            </div>`;
          form.insertAdjacentElement("beforebegin", bubble);
          input.value = "";
        })
        .catch(() => form.submit()); // fall back to a normal POST if fetch fails
    });
  });

  // Share: native share sheet where available, else copy link to clipboard.
  document.querySelectorAll(".js-share").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const url = btn.dataset.url;
      if (navigator.share) {
        navigator.share({ title: "MyPlatoon", url: url }).catch(() => {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
          const original = btn.innerHTML;
          btn.innerHTML = '<i class="fa-solid fa-check"></i> Link copied';
          setTimeout(() => { btn.innerHTML = original; }, 1800);
        });
      }
    });
  });
}

function submitReaction(form, reactionType) {
  const article = form.closest(".p5-post");
  fetch(form.action, {
    method: "POST",
    headers: { "X-Requested-With": "fetch" },
    body: new URLSearchParams({ csrf_token: csrfFrom(form), reaction_type: reactionType }),
  })
    .then((r) => r.json())
    .then((data) => {
      updateReactionButton(article, data.your_reaction);
      form.querySelector('input[name="reaction_type"]').value = data.your_reaction || "like";
      const statsEl = article.querySelector(".p5-post-stats span:first-child");
      if (statsEl && data.total !== undefined) {
        let emojis = "";
        Object.keys(data.counts || {}).forEach((k) => { emojis += REACTION_EMOJI[k] || ""; });
        statsEl.textContent = (emojis ? emojis + " " : "") + data.total;
      }
    })
    .catch(() => form.submit()); // fall back to a normal POST if fetch fails
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
