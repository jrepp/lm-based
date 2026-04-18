%% professional-book.cls
%% LaTeX class file for professional technical books
%% Uses only BasicTeX packages - no extra dependencies

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{professional-book}[2025/11/20 Professional Technical Book Class]

% Base on book class
\LoadClass[10pt,openright]{book}

% Required packages (all available in BasicTeX)
\RequirePackage{fontspec}
\RequirePackage[paperwidth=7in,paperheight=9.25in,top=0.75in,bottom=0.75in,inner=0.75in,outer=0.6in]{geometry}
\RequirePackage{xcolor}
\RequirePackage{graphicx}
\RequirePackage{fancyhdr}
\RequirePackage{fancyvrb}
\RequirePackage{caption}
\RequirePackage{hyperref}
\RequirePackage{booktabs}
\RequirePackage{longtable}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{tikz}

% Import common ISOF packages (componentized documentation framework)
\makeatletter
\def\input@path{{./}}
\makeatother
\RequirePackage{isof-colors}
\RequirePackage{isof-code}
\RequirePackage{isof-boxes}

% Hyperlink setup
\hypersetup{
    colorlinks=true,
    linkcolor=primarycolor,
    urlcolor=primarycolor,
    citecolor=medgray,
    bookmarksnumbered=true,
    bookmarksopen=true,
    pdfstartview=FitH
}

% Page style with running headers
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[LO]{\nouppercase{\rightmark}}
\fancyhead[RE]{\nouppercase{\leftmark}}
\renewcommand{\headrulewidth}{0pt}
\fancypagestyle{plain}{%
    \fancyhf{}
    \fancyfoot[C]{\thepage}
    \renewcommand{\headrulewidth}{0pt}
}

% Chapter formatting
\makeatletter
\renewcommand{\@makechapterhead}[1]{%
  \vspace*{20pt}%
  {\parindent \z@ \raggedright \normalfont
    \ifnum \c@secnumdepth >\m@ne
      \if@mainmatter
        \huge\bfseries\sffamily\color{medgray} \thechapter
        \par\nobreak
        \vskip 10\p@
      \fi
    \fi
    \interlinepenalty\@M
    \Huge \bfseries\sffamily #1\par\nobreak
    \vskip 40\p@
  }}
\makeatother

% Section formatting
\makeatletter
\renewcommand\section{\@startsection{section}{1}{\z@}%
  {-3.5ex \@plus -1ex \@minus -.2ex}%
  {2.3ex \@plus.2ex}%
  {\normalfont\Large\bfseries\sffamily\color{darkgray}}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
  {-3.25ex\@plus -1ex \@minus -.2ex}%
  {1.5ex \@plus .2ex}%
  {\normalfont\large\bfseries\sffamily\color{medgray}}}
\renewcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}%
  {-3.25ex\@plus -1ex \@minus -.2ex}%
  {1.5ex \@plus .2ex}%
  {\normalfont\normalsize\bfseries\sffamily\color{medgray}}}
\makeatother

% Code styling and box environments imported from common packages
% (isof-code.sty and isof-boxes.sty)

% Figure captions
\captionsetup{
    font={small,sf},
    labelfont={bf,sf},
    labelsep=period,
    justification=justified,
    singlelinecheck=false
}

% Table style
\renewcommand{\arraystretch}{1.3}

% Title page with overlaid text (no background image)
\RequirePackage{eso-pic}
\renewcommand{\maketitle}{
    \AddToShipoutPictureBG*{%
        \AtPageLowerLeft{%
            \textcolor{isofblue}{\rule{\paperwidth}{\paperheight}}%
        }%
    }%
    \AddToShipoutPictureFG*{%
        \AtPageLowerLeft{%
            \put(54,28){%
                \begin{tikzpicture}
                    \node[fill=black!70, rounded corners=6pt, inner sep=8pt] {%
                        \parbox{5.3in}{%
                            \centering\color{white}\LARGE\sffamily\bfseries Jacob Repp \quad jrepp@ibm.com\strut%
                        }%
                    };
                \end{tikzpicture}%
            }%
        }%
    }%
    % DRAFT banner on title page (Indiana Jones style - dramatic angled stamp)
    \AddToShipoutPictureFG*{%
        \AtPageUpperLeft{%
            \put(240,-400){%
                \rotatebox{-15}{%
                    \fboxsep=8pt%
                    \fboxrule=4pt%
                    \fcolorbox{draftred}{white}{%
                        \parbox{2.8in}{%
                            \centering\color{draftred}\fontsize{36}{40}\selectfont\sffamily\bfseries DRAFT\\[2pt]%
                            \fontsize{14}{16}\selectfont v\bookversion%
                        }%
                    }%
                }%
            }%
        }%
    }%
    \thispagestyle{empty}
    \mbox{}
    \clearpage
}

% Table of contents styling
\renewcommand{\contentsname}{\sffamily\bfseries Table of Contents}

% ============================================
% DRAFT MODE - Watermarks and indicators
% ============================================

% Add DRAFT watermark to every page (background)
\AddToShipoutPictureBG{%
    \AtPageCenter{%
        \rotatebox{45}{%
            \scalebox{8}{%
                \textcolor{draftcolor!30}{DRAFT}%
            }%
        }%
    }%
}

\endinput
